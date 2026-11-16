import json

import numpy as np
import pandas as pd
import pytest

from backtester import cli
from backtester.data.cache import Cache, from_csv, normalise_bars
from backtester.data.ibkr import parse_ibkr_history
from backtester.data.yahoo import parse_yahoo_chart

# Shape of a real Interactive Brokers connector response (SPY, pulled 2026-11-13).
IBKR = {"chart_step": 86400, "source": "Last",
        "time": ["2026-11-10T14:30:00Z", "2026-11-11T14:30:00Z", "2026-11-12T14:30:00Z"],
        "volume": [26825045, 24402394, 23599074],
        "open": [747.93, 756.74, 753.99], "close": [749.92, 759.81, 757.12],
        "high": [752.14, 762.51, 763.04], "low": [744.86, 754.9, 753.67]}


def test_parse_ibkr_history():
    bars, interval = parse_ibkr_history(IBKR)
    assert interval == "1d"
    assert len(bars) == 3
    assert bars.index[0] == pd.Timestamp("2026-11-10 14:30", tz="UTC")
    assert bars["close"].tolist() == [749.92, 759.81, 757.12]
    assert (bars["adj_factor"] == 1.0).all()
    five = parse_ibkr_history({**IBKR, "chart_step": 300})[1]
    assert five == "5m"


def test_parse_ibkr_rejects_bad_payloads():
    with pytest.raises(ValueError):
        parse_ibkr_history({"chart_step": 86400, "time": []})
    with pytest.raises(ValueError):
        parse_ibkr_history({**IBKR, "open": [1.0]})
    with pytest.raises(ValueError):
        parse_ibkr_history({**IBKR, "chart_step": 77})


def test_parse_yahoo_chart_computes_adjustment_and_drops_empty_bars():
    payload = {"chart": {"error": None, "result": [{
        "timestamp": [1704205800, 1704292200, 1704378600],
        "indicators": {"quote": [{"open": [10, None, 12], "high": [11, None, 13], "low": [9, None, 11],
                                  "close": [10, None, 12], "volume": [100, None, 300]}],
                       "adjclose": [{"adjclose": [9, None, 12]}]}}]}}
    bars = parse_yahoo_chart(payload)
    assert len(bars) == 2
    assert bars["adj_factor"].tolist() == pytest.approx([0.9, 1.0])
    with pytest.raises(ValueError):
        parse_yahoo_chart({"chart": {"error": {"code": "Not Found"}, "result": None}})


def test_normalise_bars_validates():
    idx = pd.to_datetime(["2024-01-03", "2024-01-02", "2024-01-02"])
    df = pd.DataFrame({"Open": [3, 1, 2], "High": [3, 1, 2], "Low": [3, 1, 2], "Close": [3, 1, 2]}, index=idx)
    out = normalise_bars(df)
    assert out["close"].tolist() == [2.0, 3.0]                  # sorted, last duplicate kept
    assert str(out.index.tz) == "UTC"
    with pytest.raises(ValueError):
        normalise_bars(df.assign(Close=[0, 1, 2]))
    with pytest.raises(ValueError):
        normalise_bars(df.drop(columns="Low"))


def test_cache_round_trip_merge_and_metadata(tmp_path, bars):
    cache = Cache(tmp_path)
    first = bars([1, 2, 3])
    cache.save("spy", "1d", first, source="ibkr")
    later = bars([30, 40], start=first.index[-1])               # overlaps the last bar
    merged = cache.save("SPY", "1d", later, source="ibkr")
    assert merged["close"].tolist() == [1, 2, 30, 40]            # newer value wins on overlap
    meta = cache.meta("SPY", "1d")
    assert meta["source"] == "ibkr" and meta["bars"] == 4 and meta["lean_resolution"] == "daily"
    assert cache.load("SPY", "1d", start=first.index[1], end=first.index[2].date()).shape[0] == 2
    # a different source replaces rather than mixes
    replaced = cache.save("SPY", "1d", bars([7, 8]), source="yahoo")
    assert len(replaced) == 2 and cache.meta("SPY", "1d")["source"] == "yahoo"
    assert [r["symbol"] for r in cache.list()] == ["SPY"]
    with pytest.raises(FileNotFoundError):
        cache.load("QQQ", "1d")
    with pytest.raises(ValueError):
        cache.load("SPY", "7m")


def test_from_csv(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Date,Open,High,Low,Close,Adj Close,Volume\n2024-01-02,10,11,9,10,9,100\n2024-01-03,10,12,10,12,12,200\n")
    bars = from_csv(p)
    assert bars["adj_factor"].tolist() == pytest.approx([0.9, 1.0])
    assert bars["volume"].tolist() == [100, 200]


def test_cli_end_to_end(tmp_path, capsys):
    cache_dir, runs = tmp_path / "cache", tmp_path / "runs"
    rng = np.random.default_rng(3)
    n = 400
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0008, 0.01, n)))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    times = pd.date_range("2023-01-03 14:30", periods=n, freq="B", tz="UTC")
    payload = {"chart_step": 86400, "time": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in times],
               "open": opens.tolist(), "close": closes.tolist(),
               "high": np.maximum(opens, closes).tolist(), "low": np.minimum(opens, closes).tolist(),
               "volume": [1000] * n}
    f = tmp_path / "spy.json"
    f.write_text(json.dumps(payload))

    cli.main(["--cache", str(cache_dir), "ingest-ibkr", "SPY", str(f)])
    cli.main(["--cache", str(cache_dir), "data"])
    assert "source=ibkr" in capsys.readouterr().out

    cli.main(["--cache", str(cache_dir), "run", "strategies/examples/sma_cross.py",
              "--param", "fast=10", "--param", "slow=30", "--out", str(runs),
              "--costs", str(tmp_path / "missing.toml")])
    out = capsys.readouterr().out
    assert "SmaCross" in out and "Total return" in out and "Benchmark" in out
    assert "unconfirmed" in out                                   # cost placeholder is disclosed
    run_dir = next(runs.iterdir())
    metrics = json.loads((run_dir / "metrics.json").read_text())
    meta = json.loads((run_dir / "meta.json").read_text())
    assert metrics["trades"] > 0 and meta["params"] == {"fast": 10, "slow": 30}
    assert meta["data"]["SPY"]["source"] == "ibkr" and meta["backend"] == "native"


def test_param_parsing_handles_booleans_numbers_and_text():
    got = cli._parse_params(["a=True", "b=false", "c=None", "d=3", "e=0.25", "f=black_litterman", "g=[1, 2]"])
    assert got == {"a": True, "b": False, "c": None, "d": 3, "e": 0.25, "f": "black_litterman", "g": [1, 2]}
    assert got["b"] is False and got["a"] is True
