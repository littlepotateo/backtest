"""Any strategy can trade other symbols from the command line or the New backtest form, and a run whose data cannot
support it stops with a plain message that names the date to change."""

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backtester import cli
from backtester.data.coverage import coverage
from backtester.data.cache import Cache
from backtester.engine.strategy import Strategy
from backtester.errors import CodedError
from backtester.web import jobs as J
from backtester.web.app import create_app

ROOT = Path(__file__).resolve().parent.parent


def ingest(cache_dir: Path, symbol: str, start: str, n: int = 400, tmp: Path = None):
    """Put synthetic daily bars for `symbol` into the cache (through the real ingest command)."""
    closes = 100 + np.cumsum(np.full(n, 0.1))
    times = pd.date_range(start, periods=n, freq="B", tz="UTC")
    payload = {"chart_step": 86400, "time": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in times],
               "open": closes.tolist(), "close": closes.tolist(), "high": closes.tolist(), "low": closes.tolist(),
               "volume": [1000] * n}
    f = tmp / f"{symbol}.json"
    f.write_text(json.dumps(payload))
    cli.main(["--cache", str(cache_dir), "ingest-ibkr", symbol, str(f)])


@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / "cache"
    ingest(d, "SPY", "2023-01-03 14:30", tmp=tmp_path)
    ingest(d, "QQQ", "2023-01-03 14:30", tmp=tmp_path)
    return d


def regime_cls():
    import importlib.util
    spec = importlib.util.spec_from_file_location("regime_x", ROOT / "strategies" / "regime_optimal" / "strategy.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.RegimeOptimal


def test_the_override_replaces_only_the_symbol_list_and_refuses_option_strategies():
    class Simple(Strategy):
        universe = ["SPY"]
        interval = "1d"
    sub = Simple.with_universe(["QQQ", "SPY"])
    assert sub.universe == ["QQQ", "SPY"] and Simple.universe == ["SPY"] and sub.__name__ == "Simple"
    class WithOptions(Simple):
        options_on = ["SPY"]
    with pytest.raises(ValueError, match="cannot be changed here"):
        WithOptions.with_universe(["QQQ"])


def test_a_start_before_the_data_gives_the_earliest_usable_start(cache_dir):
    cache = Cache(cache_dir)
    cls = type("S", (Strategy,), {"universe": ["SPY"], "interval": "1d"})
    c = coverage(cls, {}, ["SPY"], "1d", "2020-01-02", cache)
    assert not c["ok"] and "after the run's start 2020-01-02" in c["problems"][0]
    ok = coverage(cls, {}, ["SPY"], "1d", "2023-06-01", cache)
    assert ok["ok"] and ok["earliest_start"] >= "2023-01-03"


def test_a_missing_download_is_named_with_the_advice(cache_dir):
    c = coverage(type("S", (Strategy,), {"universe": ["XYZ"], "interval": "1d"}), {}, ["XYZ"], "1d", None, Cache(cache_dir))
    assert not c["ok"] and "not downloaded yet" in c["problems"][0] and "bt fetch-yahoo XYZ" in c["problems"][0]


def test_the_regime_training_window_gives_the_earliest_usable_train_end(cache_dir):
    cls = regime_cls()
    assert cls.history_needed({"train_end": "1968-12-31"}) == "1967-11-30"
    c = coverage(cls, {}, ["SPY"], "1d", None, Cache(cache_dir))
    assert not c["ok"] and "training window" in c["problems"][0] and "train_end" in c["problems"][0]
    assert c["earliest_train_end"] >= "2024-01-01"                         # the data starts in 2023 plus 13 months


def test_run_on_another_symbol_trades_it(cache_dir, tmp_path, capsys):
    cli.main(["--cache", str(cache_dir), "run", "strategies/examples/sma_cross.py", "--symbol", "QQQ",
              "--param", "fast=10", "--param", "slow=30", "--out", str(tmp_path / "runs"),
              "--costs", str(tmp_path / "none.toml")])
    run = next((tmp_path / "runs").iterdir())
    assert json.loads((run / "meta.json").read_text())["universe"] == ["QQQ"]
    out = capsys.readouterr().out
    assert "placed no orders" not in out                                    # QQQ, the only symbol, was traded


def test_a_symbol_in_the_list_that_is_never_traded_is_noted(cache_dir, tmp_path, capsys):
    cli.main(["--cache", str(cache_dir), "run", "strategies/examples/sma_cross.py", "--symbol", "SPY,QQQ",
              "--param", "fast=10", "--param", "slow=30", "--out", str(tmp_path / "runs"),
              "--costs", str(tmp_path / "none.toml")])
    assert "Note: QQQ was in the universe but the strategy placed no orders in it." in capsys.readouterr().out


def test_the_regime_run_with_too_early_data_stops_with_a_settings_message(cache_dir, tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--cache", str(cache_dir), "run", "strategies/regime_optimal/strategy.py", "--symbol", "SPY",
                  "--out", str(tmp_path / "runs"), "--costs", str(tmp_path / "none.toml")])
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "RESULT: The settings cannot be used [BT-RUN-002]" in out and "train_end" in out and "BT_OUTCOME" in out


def test_the_job_command_passes_each_symbol_and_refuses_a_bad_one(tmp_path):
    (tmp_path / "strategies").mkdir()
    (tmp_path / "strategies" / "x.py").write_text("")
    j = J.Jobs(tmp_path, tmp_path / "runs", tmp_path / "cache")
    cmd = j.command({"strategy": "strategies/x.py", "symbols": "spy, qqq"})
    assert cmd[cmd.index("--symbol") + 1] == "SPY" and cmd.count("--symbol") == 2
    with pytest.raises(J.BadRequest):
        j.command({"strategy": "strategies/x.py", "symbols": "bad symbol!"})


def test_the_coverage_endpoint_answers_for_the_form(tmp_path):
    (tmp_path / "strategies").mkdir()
    shutil.copy(ROOT / "strategies" / "examples" / "sma_cross.py", tmp_path / "strategies" / "sma_cross.py")
    ingest(tmp_path / "data" / "cache", "SPY", "2023-01-03 14:30", tmp=tmp_path)
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)
    r = client.get("/api/strategies/coverage", params={"path": "strategies/sma_cross.py", "symbols": "SPY", "start": "2023-06-01"})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["earliest_start"]
    r = client.get("/api/strategies/coverage", params={"path": "strategies/sma_cross.py", "symbols": "SPY", "start": "2020-01-02"})
    assert r.json()["ok"] is False and "after the run's start" in r.json()["problems"][0]
    r = client.get("/api/strategies/coverage", params={"path": "../etc/passwd"})
    assert r.status_code == 400 and r.json()["code"] == "BT-RUN-002"
