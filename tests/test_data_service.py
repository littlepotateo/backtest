"""Data service, error messages, project-folder detection and the doctor."""

import json
import socket
import ssl
import urllib.error

import numpy as np
import pandas as pd
import pytest

from backtester import cli, paths
from backtester.data import service, yahoo
from backtester.data.cache import Cache
from backtester.data.yahoo import DataError
from backtester.diagnostics import run_checks


def fake_bars(n=30, start="2024-01-02 14:30"):
    idx = pd.date_range(start, periods=n, freq="B", tz="UTC")
    c = 100 + np.arange(n, dtype=float)
    return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1000.0, "adj_factor": 1.0}, index=idx)


@pytest.fixture
def cache(tmp_path):
    return Cache(tmp_path / "cache")


def test_clean_symbols():
    assert service.clean_symbols("spy, qqq  ^vix;EFA") == ["SPY", "QQQ", "^VIX", "EFA"]
    assert service.clean_symbols("SPY SPY") == ["SPY"]
    for bad in ("", "  ", "SPY; rm -rf /", "a/b", "x" * 20, "../etc"):
        with pytest.raises(DataError):
            service.clean_symbols(bad)
    with pytest.raises(DataError):
        service.clean_symbols(",".join(f"S{i}" for i in range(41)))


def test_network_errors_become_plain_messages():
    err = lambda e: str(yahoo.explain_network_error(e))  # noqa: E731
    http = lambda code: urllib.error.HTTPError("u", code, "x", {}, None)  # noqa: E731
    assert "no data for that symbol" in err(http(404)) and "limiting" in err(http(429))
    assert "only keeps recent days" in err(http(422)) and "HTTP 503" in err(http(503))
    assert "certificate" in err(urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")))
    assert "Install Certificates" in err(urllib.error.URLError(ssl.SSLCertVerificationError("x")))
    assert "did not answer in time" in err(urllib.error.URLError(socket.timeout("timed out")))
    assert "online" in err(urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided")))
    assert "Could not reach" in err(urllib.error.URLError("something else"))
    assert yahoo.ssl_context().verify_mode == ssl.CERT_REQUIRED


def test_intraday_start_is_clamped_and_daily_is_not():
    start, note = yahoo.clamp_start("5m", "2015-01-01")
    assert pd.Timestamp(start) > pd.Timestamp.now() - pd.Timedelta(days=60) and "59 days" in note
    assert yahoo.clamp_start("5m", None)[1] is not None
    recent = (pd.Timestamp.now() - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    assert yahoo.clamp_start("5m", recent) == (recent, None)
    assert yahoo.clamp_start("1d", "1999-01-01") == ("1999-01-01", None)


def test_parse_yahoo_errors():
    with pytest.raises(DataError, match="no bars"):
        yahoo.parse_yahoo_chart({"chart": {"error": None, "result": [{"timestamp": None}]}})
    with pytest.raises(DataError, match="Yahoo error"):
        yahoo.parse_yahoo_chart({"chart": {"error": {"description": "Not Found"}, "result": None}})
    with pytest.raises(DataError):
        yahoo.fetch_yahoo("", "1d")
    with pytest.raises(DataError, match="does not offer"):
        yahoo.fetch_yahoo("SPY", "7m")


def test_fetch_symbol_caches_and_reports(cache, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "fetch_yahoo", lambda s, i, start, allow_nonpositive=False: calls.append((s, i, start, allow_nonpositive)) or fake_bars())
    log = []
    r = service.fetch_symbol(cache, "spy", "1d", "2024-01-01", log.append)
    assert r["symbol"] == "SPY" and r["bars"] == 30 and cache.has("SPY", "1d")
    assert log[0].startswith("Downloading SPY") and "30 bars cached" in log[-1]
    assert calls == [("SPY", "1d", "2024-01-01", False)]
    rates = service.fetch_rates(cache, log=log.append)
    assert calls[-1][0] == "^IRX" and calls[-1][3] is True and "Treasury bill yield" in rates["message"]


def test_fetch_many_carries_on_after_a_failure(cache, monkeypatch):
    def fake(s, i, start, allow_nonpositive=False):
        if s == "BAD":
            raise DataError("no data")
        return fake_bars()
    monkeypatch.setattr(service, "fetch_yahoo", fake)
    log = []
    r = service.fetch_many(cache, ["SPY", "BAD", "QQQ"], log=log.append)
    assert [d["symbol"] for d in r["done"]] == ["SPY", "QQQ"] and r["failed"] == [("BAD", "no data")]
    assert any("BAD: FAILED" in x for x in log)


def test_update_all_restarts_a_week_before_the_last_bar(cache, monkeypatch):
    cache.save("SPY", "1d", fake_bars(), source="yahoo")
    cache.save("MANUAL", "1d", fake_bars(), source="csv")
    end_before = pd.Timestamp(cache.meta("SPY", "1d")["end"])
    starts = []
    monkeypatch.setattr(service, "fetch_yahoo", lambda s, i, start, allow_nonpositive=False: starts.append((s, start)) or fake_bars(40))
    r = service.update_all(cache)
    assert [s for s, _ in starts] == ["SPY"]                 # only Yahoo datasets are refreshed
    assert starts[0][1] == (end_before - pd.Timedelta(days=7)).strftime("%Y-%m-%d") and len(r["done"]) == 1
    assert pd.Timestamp(cache.meta("SPY", "1d")["end"]) > end_before        # the new bars were merged in
    empty = []
    service.update_all(Cache(cache.root.parent / "other"), empty.append)
    assert "Nothing to update" in empty[0]


def test_import_csv_and_ibkr_json(cache):
    df = fake_bars()
    csv = df.reset_index().rename(columns={"index": "time"}).drop(columns="adj_factor").to_csv(index=False)
    r = service.import_file(cache, "QQQ.csv", csv.encode())
    assert r["symbol"] == "QQQ" and r["interval"] == "1d" and cache.meta("QQQ", "1d")["source"] == "csv"
    ib = {"chart_step": 86400, "time": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in df.index], "open": df.open.tolist(),
          "high": df.high.tolist(), "low": df.low.tolist(), "close": df.close.tolist(), "volume": df.volume.tolist()}
    r = service.import_file(cache, "whatever.json", json.dumps(ib).encode(), symbol="IWM")
    assert r["symbol"] == "IWM" and cache.meta("IWM", "1d")["source"] == "ibkr"
    with pytest.raises(DataError, match="only .csv and .json"):
        service.import_file(cache, "SPY.xlsx", b"x")
    with pytest.raises(DataError, match="could not be read"):
        service.import_file(cache, "SPY.csv", b"not,a,price,file\n1,2,3,4")
    with pytest.raises(DataError, match="could not be read"):
        service.import_file(cache, "SPY.json", b"{nope")
    with pytest.raises(DataError, match="Could not tell which symbol"):
        service.import_file(cache, "!!!.csv", csv.encode())


def test_dataset_table_and_delete(cache):
    cache.save("SPY", "1d", fake_bars(), source="yahoo")
    old = fake_bars(5, "2010-01-04 14:30")
    cache.save("^IRX", "1d", old, source="yahoo", allow_nonpositive=True)
    rows = service.dataset_table(cache)
    assert [r["symbol"] for r in rows] == ["SPY", "^IRX"] and rows[0]["kind"] == "prices" and rows[1]["kind"] == "rate"
    assert rows[1]["stale"] and rows[1]["age_days"] > 1000
    service.delete_dataset(cache, "SPY", "1d")
    assert not cache.has("SPY", "1d") and not (cache.root / "SPY").exists()
    with pytest.raises(DataError):
        service.delete_dataset(cache, "SPY", "1d")


def test_project_root_detection(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    (proj / "sub" / "deeper").mkdir(parents=True)
    (proj / "pyproject.toml").write_text('[project]\nname = "backtester"\n')
    monkeypatch.delenv("BACKTEST_HOME", raising=False)
    monkeypatch.chdir(proj / "sub" / "deeper")
    assert paths.find_root() == proj.resolve()                # found by walking up from where the command runs
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.setenv("BACKTEST_HOME", str(other))
    assert paths.find_root() == other.resolve()
    monkeypatch.delenv("BACKTEST_HOME")
    (proj / "pyproject.toml").write_text('[project]\nname = "something-else"\n')
    monkeypatch.chdir(other)
    assert paths.find_root() not in (proj, proj.resolve())   # a different project's pyproject.toml is not ours


def test_cli_fetch_prints_progress_and_fails_loudly(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(service, "fetch_yahoo", lambda s, i, start, allow_nonpositive=False: fake_bars())
    cli.main(["--cache", str(tmp_path / "c"), "fetch-yahoo", "SPY", "--start", "2024-01-01"])
    out = capsys.readouterr().out
    assert "Saving to" in out and "Downloading SPY" in out and "30 bars cached" in out

    def boom(*a, **k):
        raise DataError("Yahoo Finance has no data for that symbol (HTTP 404).")
    monkeypatch.setattr(service, "fetch_yahoo", boom)
    with pytest.raises(SystemExit) as e:
        cli.main(["--cache", str(tmp_path / "c"), "fetch-yahoo", "NOPE"])
    assert "no data for that symbol" in str(e.value) and e.value.code != 0
    with pytest.raises(SystemExit) as e:
        cli.main(["--cache", str(tmp_path / "c"), "fetch-rates"])
    assert e.value.code != 0


def test_doctor_reports_each_check(cache):
    checks = run_checks(cache, network=False)
    names = [c["name"] for c in checks]
    assert {"Python version", "Project folder", "Installed packages", "Cached datasets"} <= set(names)
    assert all({"name", "ok", "detail", "hint"} <= set(c) for c in checks)
    assert next(c for c in checks if c["name"] == "Python version")["ok"]
    assert next(c for c in checks if c["name"] == "Installed packages")["ok"]
