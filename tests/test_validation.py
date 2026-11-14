"""Tests for the engine-driven validation tests: grid search, walk-forward, Monte Carlo,
checks, cost stress, regimes, interest and delayed fills, and the validate command."""

import json

import numpy as np
import pandas as pd
import pytest

from backtester import Strategy, cli
from backtester.analysis import checks, coststress, montecarlo, regimes
from backtester.analysis.findings import flags, to_jsonable, validate
from backtester.analysis.optimize import daily_returns, grid_search, trial_count
from backtester.analysis.walkforward import (in_out_of_sample, make_windows, sensitivity,
                                             walk_forward)
from backtester.engine import CostModel, RunConfig, Runner

ZERO = CostModel.zero()


class Hold(Strategy):
    universe = ["A"]

    def on_bar(self, ctx):
        if ctx.position("A") == 0:
            ctx.order_target_percent("A", 1.0)


class Trend(Strategy):
    """Long when the close is above its `n`-bar average."""
    universe = ["A"]
    params = {"n": 20}
    param_grid = {"n": [5, 10, 20, 40]}

    def on_bar(self, ctx):
        c = ctx.closes("A", self.params["n"])
        if len(c) == self.params["n"]:
            ctx.order_target_percent("A", 1.0 if c[-1] > c.mean() else 0.0)


class Flip(Strategy):
    """Long if `side` is 1, short if -1: the right side changes halfway through the data."""
    universe = ["A"]
    params = {"side": 1}
    param_grid = {"side": [1, -1]}

    def on_bar(self, ctx):
        ctx.order_target_percent("A", 0.9 * self.params["side"])


class Cheat(Strategy):
    """Reaches past the Context into the engine's full price table to read tomorrow's
    close: must be caught."""
    universe = ["A"]

    def on_bar(self, ctx):
        closes = ctx._sim.data["A"]["close"]
        nxt = closes[closes.index > ctx.now]
        if len(nxt):
            ctx.order_target_percent("A", 1.0 if nxt.iloc[0] > ctx.price("A") else 0.0)


def trending(bars, n=600, seed=0, drift=0.0005, vol=0.01):
    rng = np.random.default_rng(seed)
    return bars(100 * np.exp(np.cumsum(rng.normal(drift, vol, n))))


def runner(cls, data, **cfg):
    cfg.setdefault("costs", ZERO)
    return Runner(cls, RunConfig(**cfg), data=data)


# --- engine additions ---------------------------------------------------------------------

def test_cash_and_margin_interest(bars):
    data = {"A": bars(np.full(260, 100.0), start="2024-01-02 14:30")}
    rates = pd.Series(0.05, index=pd.date_range("2023-01-01", "2026-01-01"))

    class Idle(Strategy):
        universe = ["A"]

        def on_bar(self, ctx):
            pass

    r = Runner(Idle, RunConfig(costs=ZERO), data=data, rates=rates).run()
    days = (r.equity.index[-1] - r.equity.index[0]).days
    assert r.equity.iloc[-1] == pytest.approx(100_000 * (1 + 0.04 / 365) ** days, rel=1e-4)   # 5% - 1%
    assert r.meta["interest"]["earned"] == pytest.approx(r.equity.iloc[-1] - 100_000)
    off = Runner(Idle, RunConfig(costs=ZERO, cash_interest=False), data=data, rates=rates).run()
    assert off.equity.iloc[-1] == 100_000
    none = Runner(Idle, RunConfig(costs=ZERO), data=data).run()
    assert none.equity.iloc[-1] == 100_000 and any("interest" in n for n in none.meta["notes"])

    class Levered(Strategy):
        universe = ["A"]

        def on_bar(self, ctx):
            if ctx.position("A") == 0:
                ctx.order("A", 2000)                                  # $200k of stock on $100k

    lev = Runner(Levered, RunConfig(costs=ZERO, max_leverage=2.0), data=data, rates=rates).run()
    held = (lev.equity.index[-1] - lev.equity.index[1]).days
    owed = 100_000 * ((1 + 0.075 / 365) ** held - 1)                  # 5% + 2.5%, compounding
    assert lev.meta["interest"]["paid"] == pytest.approx(owed, rel=0.01)
    assert lev.equity.iloc[-1] < 100_000


def test_fill_delay_moves_fills_one_bar_later(bars):
    data = {"A": bars([10, 11, 12, 13, 14], opens=[10, 10.5, 11.5, 12.5, 13.5])}
    base = runner(Hold, data, fractional_shares=True).run()
    late = runner(Hold, data, fractional_shares=True, fill_delay_bars=1).run()
    assert base.fills.iloc[0]["time"] == data["A"].index[1] and base.fills.iloc[0]["price"] == 10.5
    assert late.fills.iloc[0]["time"] == data["A"].index[2] and late.fills.iloc[0]["price"] == 11.5


def test_strategy_grid_respects_valid_params():
    class S(Strategy):
        params = {"fast": 1, "slow": 2, "x": 9}
        param_grid = {"fast": [1, 5], "slow": [2, 5]}

        @classmethod
        def valid_params(cls, p):
            return p["fast"] < p["slow"]

    assert S.grid() == [{"fast": 1, "slow": 2, "x": 9}, {"fast": 1, "slow": 5, "x": 9}]
    assert Hold.grid() == [{}]


# --- grid search and ledger -----------------------------------------------------------------

def test_grid_search_and_trial_ledger(bars, tmp_path):
    ledger = tmp_path / "t.jsonl"
    r = runner(Trend, {"A": trending(bars)})
    g = grid_search(r, ledger=ledger)
    assert len(g["configs"]) == 4 and g["returns"].shape[1] == 4
    assert g["table"].loc[g["best"], "sharpe"] == g["table"]["sharpe"].max()
    assert trial_count(ledger) == 4
    grid_search(r, ledger=ledger)                                  # same variants again
    assert trial_count(ledger) == 4
    grid_search(r, grid=[{"n": 7}], ledger=ledger)                 # a new one
    assert trial_count(ledger) == 5
    assert trial_count(tmp_path / "missing.jsonl") == 0


# --- walk-forward -----------------------------------------------------------------------------

def test_windows_tile_without_overlap_or_leakage():
    w = make_windows(1000, is_days=400, oos_days=100)
    assert w[0] == (0, 400, 400, 500) and w[1] == (100, 500, 500, 600)
    assert [x[2] for x in w] == [400, 500, 600, 700, 800, 900]
    for (is_s, is_e, oos_s, oos_e), nxt in zip(w, w[1:] + [None]):
        assert is_e <= oos_s                                         # in-sample ends before OOS starts
        if nxt:
            assert oos_e == nxt[2]                                   # OOS segments tile exactly
    anchored = make_windows(1000, 400, 100, mode="anchored")
    assert all(x[0] == 0 for x in anchored) and anchored[-1][1] == 900
    assert len(make_windows(2520)) >= 5                              # defaults give at least five
    with pytest.raises(ValueError):
        make_windows(50, 400, 100)


def test_parameter_free_walk_forward_equals_a_plain_backtest(bars):
    data = {"A": trending(bars, 700)}
    r = runner(Hold, data, fractional_shares=True)
    wf = walk_forward(r, grid_search(r), is_days=200, oos_days=100)
    plain = r.run(start=wf["windows"].iloc[0]["oos_start"])
    pd.testing.assert_series_equal(wf["oos_equity"], plain.equity)
    assert wf["distinct_params_chosen"] == 1
    assert len(wf["windows"]) == 5


def test_walk_forward_adapts_when_the_best_parameter_changes(bars):
    up = 100 * np.exp(np.cumsum(np.full(400, 0.002)))
    down = up[-1] * np.exp(np.cumsum(np.full(400, -0.002)))
    data = {"A": bars(np.concatenate([up, down]))}
    r = runner(Flip, data, fractional_shares=True)
    g = grid_search(r)
    rolling = walk_forward(r, g, is_days=100, oos_days=50, mode="rolling")
    anchored = walk_forward(r, g, is_days=100, oos_days=50, mode="anchored")
    sides = [p["side"] for p in rolling["windows"]["params"]]
    assert sides[0] == 1 and sides[-1] == -1                         # switches to short
    switch_rolling = sides.index(-1)
    switch_anchored = [p["side"] for p in anchored["windows"]["params"]].index(-1) \
        if -1 in [p["side"] for p in anchored["windows"]["params"]] else 99
    assert switch_rolling < switch_anchored                          # anchored adapts later
    assert rolling["oos_total_return"] > anchored["oos_total_return"]
    assert rolling["param_instability"]["side"] > 0
    # no out-of-sample day is ever inside its own in-sample window
    for _, row in rolling["windows"].iterrows():
        assert row["is_end"] < row["oos_start"]


def test_pure_noise_looks_good_in_sample_and_not_out_of_sample(bars):
    is_sharpes, oos_sharpes = [], []
    for seed in range(8):
        r = runner(Trend, {"A": trending(bars, 900, seed=seed, drift=0.0)})
        g = grid_search(r)
        wf = walk_forward(r, g, is_days=200, oos_days=100)
        is_sharpes.append(wf["is_sharpe_mean"])
        oos_sharpes.append(wf["oos_sharpe"])
    assert np.mean(is_sharpes) > 0.3                                 # picking the best flatters
    assert np.mean(oos_sharpes) < np.mean(is_sharpes) - 0.3


def test_in_out_of_sample_and_sensitivity(bars):
    r = runner(Trend, {"A": trending(bars, 800, seed=3)})
    g = grid_search(r)
    io = in_out_of_sample(r, g, 0.7)
    assert io["split_date"] == str(g["returns"].index[int(800 * 0.7)].date())
    assert io["params"] in g["configs"]
    s = sensitivity(Trend, g)
    best_n = s["best_params"]["n"]
    values = Trend.param_grid["n"]
    assert len(s["neighbours"]) == (1 if best_n in (values[0], values[-1]) else 2)
    assert 0 <= s["share_of_grid_positive"] <= 1


# --- Monte Carlo ------------------------------------------------------------------------------

def test_reshuffle_keeps_final_equity_and_changes_drawdown(bars):
    res = runner(Trend, {"A": trending(bars, 1500, seed=5, vol=0.02)}).run()
    assert len(res.trades) > 20
    mc = montecarlo.monte_carlo(res, n_paths=500, seed=1)
    tr = mc["reshuffle"]["total_return"]
    assert tr["p5"] == pytest.approx(tr["p95"])                      # same trades, same end point
    dd = mc["reshuffle"]["max_drawdown"]
    assert dd["p95"] < dd["p50"] < dd["p5"] <= 0                     # but drawdowns differ
    assert mc["skip"]["total_return"]["p5"] != pytest.approx(mc["skip"]["total_return"]["p95"])
    again = montecarlo.monte_carlo(res, n_paths=500, seed=1)
    assert again["bootstrap"]["total_return"] == mc["bootstrap"]["total_return"]   # reproducible
    other = montecarlo.monte_carlo(res, n_paths=500, seed=2)
    assert other["bootstrap"]["total_return"] != mc["bootstrap"]["total_return"]


def test_bootstrap_centres_on_the_backtest_and_ruin_matches_theory(bars):
    res = runner(Hold, {"A": trending(bars, 2000, seed=6)}, fractional_shares=True).run()
    mc = montecarlo.monte_carlo(res, n_paths=2000, seed=0)
    b = mc["bootstrap"]
    assert b["total_return"]["p5"] < mc["backtest_total_return"] < b["total_return"]["p95"]
    assert 0 <= b["probability_of_loss"] <= 1 and len(b["fan"]["p50"]) > 10
    # symmetric +/-1% coin flips: chance of a 20% drawdown at some point in 400 steps
    rng = np.random.default_rng(7)
    flips = np.where(rng.random((4000, 400)) < 0.5, 0.01, -0.01)
    wealth = np.cumprod(1 + flips, axis=1)
    ours = (montecarlo._drawdowns(wealth) <= -0.20).mean()
    peaks = np.maximum.accumulate(np.concatenate([np.ones((4000, 1)), wealth], axis=1), axis=1)
    direct = ((np.concatenate([np.ones((4000, 1)), wealth], axis=1) / peaks - 1).min(axis=1) <= -0.20).mean()
    assert ours == direct and 0.2 < ours < 0.8


def test_synthetic_bars_keep_shape_and_calendar(bars):
    df = trending(bars, 500, seed=8)
    df["high"] = df[["open", "close"]].max(axis=1) * 1.01
    df["low"] = df[["open", "close"]].min(axis=1) * 0.99
    new = montecarlo.synthetic_bars({"A": df}, np.random.default_rng(0))["A"]
    assert new.index.equals(df.index) and new["close"].iloc[0] == df["close"].iloc[0]
    assert (new["high"] >= new[["open", "close"]].max(axis=1) - 1e-9).all()
    assert (new["low"] <= new[["open", "close"]].min(axis=1) + 1e-9).all()
    assert not np.allclose(new["close"], df["close"])
    # resampled returns come from the original set of returns
    orig = set(np.round(df["close"].to_numpy()[1:] / df["close"].to_numpy()[:-1], 10))
    assert set(np.round(new["close"].to_numpy()[1:] / new["close"].to_numpy()[:-1], 10)) <= orig
    r = runner(Trend, {"A": df})
    out = montecarlo.synthetic_reruns(r, {"n": 20}, n_paths=5, seed=0)
    assert out["paths"] == 5 and "p50" in out["total_return"]


# --- checks -----------------------------------------------------------------------------------

def test_lookahead_test_catches_a_cheat_and_passes_an_honest_strategy(bars):
    df = trending(bars, 400, seed=9)
    assert checks.lookahead_test(runner(Trend, {"A": df}))["passed"]
    res = checks.lookahead_test(runner(Cheat, {"A": df}))
    assert not res["passed"] and res["problem"] is not None
    assert checks.lookahead_test(runner(Trend, {"A": df}, fill="close"))["same_bar_fills"]


def test_data_quality_and_trade_checks(bars):
    df = trending(bars, 300, seed=10)
    assert checks.data_quality({"A": df}, "1d")["A"]["issues"] == []
    bad = df.copy()
    bad.iloc[150, bad.columns.get_loc("close")] *= 3                  # a spike
    bad.iloc[10, bad.columns.get_loc("high")] = bad.iloc[10]["low"] * 0.5
    bad = bad.drop(bad.index[200:230])                                # a hole
    issues = " ".join(checks.data_quality({"A": bad}, "1d")["A"]["issues"])
    assert "standard deviations" in issues and "high/low" in issues and "gap" in issues

    res = runner(Trend, {"A": trending(bars, 1500, seed=5, vol=0.02)}).run()
    t = checks.trade_checks(res)
    assert t["trades"] == len(res.trades)
    assert t["profit_without_best_trade"] == pytest.approx(res.trades["pnl"].sum() - res.trades["pnl"].max())
    assert 0 < t["top_5pct_share_of_gross_profit"] <= 1


# --- cost stress ------------------------------------------------------------------------------

def test_cost_stress_levels_and_break_even(bars):
    class Churn(Strategy):
        """Fixed-size round trip every four bars, so trades do not depend on costs."""
        universe = ["A"]

        def init(self, ctx):
            self.i = 0

        def on_bar(self, ctx):
            self.i += 1
            if self.i % 4 == 1:
                ctx.order_target("A", 100)
            elif self.i % 4 == 3:
                ctx.order_target("A", 0)

    data = {"A": trending(bars, 400, seed=11, drift=0.001)}
    costs = CostModel(per_share=0.01, min_per_order=0, max_pct_of_trade=0, slippage_bps=5, confirmed=True)
    r = Runner(Churn, RunConfig(costs=costs), data=data)
    cs = coststress.cost_stress(r)
    profits = [row["profit"] for row in cs["levels"]]
    assert profits[0] > profits[1] > profits[2] > profits[3]         # 0x, 1x, 2x, 3x
    assert cs["levels"][0]["costs_paid"] == 0
    assert profits[0] - profits[1] == pytest.approx(cs["levels"][1]["costs_paid"])
    be = cs["break_even_multiplier"]
    at_be = r.run(costs=costs.scaled(be))
    assert at_be.equity.iloc[-1] - 100_000 == pytest.approx(0, abs=1.0)   # zero profit at break-even
    assert cs["break_even_cost_bps_per_fill"] == pytest.approx(be * cs["assumed_cost_bps_per_fill"])
    assert cs["delayed_fill"]["profit"] != pytest.approx(profits[1])


# --- regimes ----------------------------------------------------------------------------------

def test_regime_labels_use_only_the_past(bars):
    df = trending(bars, 900, seed=12)
    full = regimes.regime_labels(df["close"])
    cut = regimes.regime_labels(df["close"].iloc[:600])
    pd.testing.assert_frame_equal(full.iloc[:600], cut)               # later data changes nothing
    assert set(full["trend"]) <= {"bull", "bear", "unknown"}
    assert (full["trend"].iloc[:200] == "unknown").all()


def test_regime_breakdown_adds_up(bars):
    up = 100 * np.exp(np.cumsum(np.full(500, 0.001)))
    down = up[-1] * np.exp(np.cumsum(np.full(300, -0.002)))
    df = bars(np.concatenate([up, down]))
    res = runner(Hold, {"A": df}, fractional_shares=True).run()
    rb = regimes.regime_breakdown(res, df["close"])
    for dim in ("trend", "volatility", "drawdown", "year"):
        assert sum(r["share_of_time"] for r in rb[dim]) == pytest.approx(1.0)
        total = np.prod([1 + r["total_return"] for r in rb[dim]]) - 1
        assert total == pytest.approx(res.equity.iloc[-1] / 100_000 - 1)
    by = {r["regime"]: r for r in rb["trend"]}
    assert by["bull"]["total_return"] > 0 > by["bear"]["total_return"]
    assert rb["missing"] == []
    only_up = bars(up)
    rb2 = regimes.regime_breakdown(runner(Hold, {"A": only_up}, fractional_shares=True).run(), only_up["close"])
    assert rb2["missing"] == ["no bear market in the sample"]


# --- everything together ----------------------------------------------------------------------

def test_validate_runs_all_tests_and_serialises(bars, tmp_path):
    df = trending(bars, 1300, seed=13, drift=0.0006, vol=0.012)
    r = runner(Trend, {"A": df})
    v = validate(r, None, benchmark_close=df["close"], ledger=tmp_path / "l.jsonl", n_paths=300)
    for key in ("metrics", "checks", "optimize", "walkforward", "in_out_of_sample", "sensitivity",
                "montecarlo", "kelly", "overfitting", "regimes", "costs", "flags"):
        assert key in v, key
    assert v["checks"]["lookahead"]["passed"]
    assert v["overfitting"]["trials_recorded"] == 4
    assert "pbo" in v["skipped"]                                      # only four configurations
    assert all(f["severity"] in ("high", "medium", "info") for f in v["flags"])
    text = json.dumps(to_jsonable(v), default=str)
    assert json.loads(text)["params"] == {"n": 20}
    # a strategy without a grid skips the grid-based tests and says so
    v2 = validate(runner(Hold, {"A": df}, fractional_shares=True), tests=["walkforward", "montecarlo"], n_paths=100)
    assert "walkforward" in v2["skipped"] and "montecarlo" in v2
    with pytest.raises(ValueError):
        validate(r, tests=["nonsense"])


def test_flags_fire_on_the_cases_they_describe():
    base = {"metrics": {"trades": 4, "total_return": -0.1}, "skipped": {}}
    msgs = [f["message"] for f in flags(base)]
    assert any("Only 4 closed trades" in m for m in msgs) and any("lost money" in m for m in msgs)
    v = {"metrics": {"trades": 100, "total_return": 0.5}, "skipped": {},
         "checks": {"lookahead": {"passed": False, "same_bar_fills": False}, "data": {}, "trades": {"trades": 100}},
         "walkforward": {"oos_sharpe": 0.1, "is_sharpe_mean": 1.0, "windows_profitable": 0.3,
                         "windows_with_too_few_trades": 0, "windows": [], "param_instability": {"n": 0.5}},
         "costs": {"levels": [{"cost_multiplier": 1.0, "profit": 100.0}, {"cost_multiplier": 2.0, "profit": -5.0}],
                   "delayed_fill": {"profit": 90.0}}}
    out = flags(v)
    text = " ".join(f["message"] for f in out)
    assert "could not have had" in text and "likely overfitted" in text and "costs are doubled" in text
    assert out[0]["severity"] == "high"                               # most serious first


def test_cli_validate_optimize_check_and_compare(tmp_path, capsys):
    cache_dir, runs = tmp_path / "cache", tmp_path / "runs"
    rng = np.random.default_rng(3)
    n = 900
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0006, 0.01, n)))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    times = pd.date_range("2021-01-04 14:30", periods=n, freq="B", tz="UTC")

    def payload(sl):
        return {"chart_step": 86400, "time": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in times[sl]],
                "open": opens[sl].tolist(), "close": closes[sl].tolist(),
                "high": np.maximum(opens, closes)[sl].tolist(), "low": np.minimum(opens, closes)[sl].tolist(),
                "volume": [1000] * len(times[sl])}

    full, sample = tmp_path / "spy.json", tmp_path / "sample.json"
    full.write_text(json.dumps(payload(slice(None))))
    sample.write_text(json.dumps(payload(slice(-10, None))))
    strat = tmp_path / "sma.py"
    strat.write_text(open("strategies/examples/sma_cross.py").read()
                     .replace('"fast": [20, 50, 100], "slow": [100, 150, 200, 250]', '"fast": [10, 20], "slow": [40, 60]'))
    common = ["--cache", str(cache_dir)]
    opts = ["--param", "fast=10", "--param", "slow=40", "--out", str(runs), "--costs", str(tmp_path / "none.toml")]

    cli.main(common + ["ingest-ibkr", "SPY", str(full)])
    cli.main(common + ["compare-ibkr", "SPY", str(sample)])
    assert "10 of 10 bars compared" in capsys.readouterr().out
    cli.main(common + ["check", str(strat)] + opts)
    assert "Look-ahead test: passed" in capsys.readouterr().out
    cli.main(common + ["optimize", str(strat)] + opts)
    assert "4 configurations" in capsys.readouterr().out
    cli.main(common + ["validate", str(strat), "--paths", "200", "--synthetic", "3"] + opts)
    out = capsys.readouterr().out
    for phrase in ("Walk-forward", "Monte Carlo", "Synthetic price histories", "Kelly",
                   "Probability true Sharpe", "Cost stress", "Regimes"):
        assert phrase in out, phrase
    run_dir = sorted(runs.iterdir())[-1]
    saved = json.loads((run_dir / "validation.json").read_text())
    assert saved["overfitting"]["trials_recorded"] == 4 and "flags" in saved
    assert (strat.with_suffix(".trials.jsonl")).exists()
