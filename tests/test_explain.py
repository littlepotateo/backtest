"""Tests for the written explanation and the paper library."""

import json

import numpy as np
import pandas as pd
import pytest

from backtester import Strategy, cli
from backtester.analysis.findings import to_jsonable, validate
from backtester.engine import CostModel, RunConfig, Runner
from backtester.explain import explain, trust_level
from backtester.research import Library, slug


class Trend(Strategy):
    universe = ["A"]
    params = {"n": 20}
    param_grid = {"n": [5, 10, 20, 40]}

    def on_bar(self, ctx):
        c = ctx.closes("A", self.params["n"])
        if len(c) == self.params["n"]:
            ctx.order_target_percent("A", 1.0 if c[-1] > c.mean() else 0.0)


def validated(bars, seed=0, drift=0.0006):
    rng = np.random.default_rng(seed)
    df = bars(100 * np.exp(np.cumsum(rng.normal(drift, 0.012, 1300))))
    r = Runner(Trend, RunConfig(costs=CostModel.zero()), data={"A": df})
    v = validate(r, None, benchmark_close=df["close"], n_paths=300)
    return to_jsonable(v), r.run().meta


def test_explanation_quotes_the_numbers_and_has_every_section(bars):
    v, meta = validated(bars)
    text = explain(v, meta, "Trend test")
    m = v["metrics"]
    assert text.startswith("# Trend test: what the backtest says")
    for heading in ("## In short", "## What drove the result", "## Does it hold up?",
                    "## Concerns, most serious first", "## What this does not tell you"):
        assert heading in text, heading
    assert f"{m['total_return'] * 100:,.1f}%" in text
    assert f"{m['max_drawdown'] * 100:,.1f}%" in text
    assert "Look-ahead check:** passed" in text
    assert "not a forecast" in text and "not investment advice" in text
    assert "Walk-forward" in text and "Monte Carlo" in text and "Costs:" in text
    for f in v["flags"]:
        assert f["message"] in text                              # every flag is listed
    assert explain(v, meta) == explain(json.loads(json.dumps(v)), meta)   # same after a JSON round trip


def test_trust_level_separates_evidence_from_risk():
    risk_only = [{"severity": "high", "test": "monte-carlo", "message": "6% of histories fall 50%."}]
    assert trust_level(risk_only)[0] == "No serious concerns raised"
    assert trust_level([{"severity": "high", "test": "look-ahead", "message": "x"}])[0] == "Unproven"
    two = [{"severity": "medium", "test": "walk-forward", "message": "a"}, {"severity": "medium", "test": "costs", "message": "b"}]
    assert trust_level(two)[0] == "Tentative"
    assert trust_level(two[:1])[0].startswith("Reasonable")
    assert trust_level([{"severity": "info", "test": "data", "message": "c"}])[0] == "No serious concerns raised"
    text = explain({"metrics": {"start": "2020-01-01", "end": "2021-01-01", "trading_days": 252, "total_return": 0.1,
                                "cagr": 0.1, "max_drawdown": -0.2, "sharpe": 0.5, "trades": 12},
                    "flags": risk_only}, {"strategy": "S"})
    assert "Risk to plan for" in text and "No serious concerns raised" in text


def test_failed_lookahead_and_costs_wording():
    base = {"metrics": {"start": "2020-01-01", "end": "2021-01-01", "trading_days": 252, "total_return": 0.5, "cagr": 0.5,
                        "max_drawdown": -0.1, "sharpe": 1.0, "trades": 40, "total_commission": 100.0, "total_slippage": 50.0},
            "flags": [], "checks": {"lookahead": {"passed": False, "same_bar_fills": False, "cuts": [], "problem": {}},
                                    "data": {}, "trades": {}}}
    assert "failed" in explain(base, {"strategy": "S"})
    lv = lambda m, r: {"cost_multiplier": m, "total_return": r}  # noqa: E731
    noisy = dict(base, costs={"levels": [lv(0.0, 5.0), lv(1.0, 4.0), lv(2.0, 4.2), lv(3.0, 4.5)],
                              "delayed_fill": {"total_return": 4.0}, "break_even_multiplier": 12.0})
    text = explain(noisy, {"strategy": "S"})
    assert "reduced total return by 100.0 percentage points" in text
    assert "no break-even cost is quoted" in text and "vanish" not in text
    steady = dict(base, costs={"levels": [lv(0.0, 5.0), lv(1.0, 4.0), lv(2.0, 3.0), lv(3.0, 2.0)],
                               "delayed_fill": {"total_return": 3.9}, "break_even_multiplier": 5.0})
    assert "vanish at about 5.0x" in explain(steady, {"strategy": "S"})


def test_next_steps_follow_the_flags():
    base = {"metrics": {"start": "2020-01-01", "end": "2021-01-01", "trading_days": 252, "total_return": -0.1, "cagr": -0.1,
                        "max_drawdown": -0.3, "sharpe": -0.5, "trades": 4},
            "flags": [{"severity": "high", "test": "trades", "message": "Only 4 closed trades."},
                      {"severity": "high", "test": "performance", "message": "The strategy lost money."}]}
    text = explain(base, {"strategy": "S"})
    assert "## What to do next" in text and "longer history" in text and "did not make money" in text


def test_paper_library_round_trip(tmp_path):
    lib = Library(tmp_path / "lib")
    assert slug("A Quantitative Approach to Tactical Asset Allocation", 2007) == "a-quantitative-approach-to-tactical-asset-alloc-2007" \
        or slug("A Quantitative Approach to Tactical Asset Allocation", 2007).endswith("-2007")
    pid = lib.add("A Quantitative Approach to Tactical Asset Allocation", authors="Faber", year=2007,
                  venue="Journal of Wealth Management", url="https://example.org/p",
                  claims=["equity-like returns with bond-like volatility and drawdown"])
    again = lib.add("A Quantitative Approach to Tactical Asset Allocation", year=2007, finding="timing helps")
    assert again == pid and lib.get(pid)["authors"] == "Faber" and lib.get(pid)["finding"] == "timing helps"
    assert lib.get(pid)["status"] == "candidate" and (tmp_path / "lib" / f"{pid}.md").exists()
    run = tmp_path / "run"
    run.mkdir()
    (run / "metrics.json").write_text(json.dumps({"start": "2007-01-01T00:00", "end": "2020-01-01T00:00", "total_return": 1.2,
                                                  "cagr": 0.06, "volatility": 0.08, "sharpe": 0.7, "max_drawdown": -0.15,
                                                  "trades": 100, "benchmark_total_return": 2.0, "benchmark_max_drawdown": -0.5}))
    (run / "meta.json").write_text(json.dumps({"strategy": "Faber", "data": {"SPY": {"source": "yahoo"}}}))
    entry = lib.link_run(pid, run)
    assert entry["strategy"] == "Faber" and lib.get(pid)["status"] == "replicating"
    lib.link_run(pid, run)                                          # linking twice does not duplicate
    assert len(lib.get(pid)["runs"]) == 1
    text = lib.compare(pid)
    assert "the abstract only" in text and "No numbers are quoted" in text and "120.0%" in text and "-15.0%" in text
    lib.set_status(pid, "partly replicated")
    assert [p["status"] for p in lib.list()] == ["partly replicated"]
    with pytest.raises(ValueError):
        lib.set_status(pid, "great")
    with pytest.raises(KeyError):
        lib.get("nope")


def test_cli_explain_and_paper(tmp_path, bars, capsys):
    v, meta = validated(bars)
    run = tmp_path / "run"
    run.mkdir()
    (run / "validation.json").write_text(json.dumps(v))
    (run / "meta.json").write_text(json.dumps(meta, default=str))
    cli.main(["explain", str(run)])
    assert "what the backtest says" in capsys.readouterr().out
    assert (run / "explanation.md").exists()
    lib = str(tmp_path / "lib")
    cli.main(["paper", "add", "--library", lib, "--title", "Test Paper", "--year", "2020", "--claim", "it works"])
    cli.main(["paper", "list", "--library", lib])
    assert "test-paper-2020" in capsys.readouterr().out
    cli.main(["paper", "status", "test-paper-2020", "rejected", "--library", lib])
    cli.main(["paper", "compare", "test-paper-2020", "--library", lib])
    assert "it works" in capsys.readouterr().out
