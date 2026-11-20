"""A failed run says whose fault it is (the strategy's code, the settings, or the program) in plain words, and a finished run
reports the strategy's result separately from the run's status."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtester import cli, outcome
from backtester.data.yahoo import DataError
from backtester.errors import CodedError
from backtester.web import jobs

BROKEN = '''from backtester import Strategy


class Broken(Strategy):
    universe = ["SPY"]
    interval = "1d"
    params = {}

    def on_bar(self, ctx):
        ctx.closes("SPY", 5)
        return 1 / 0
'''


def raised(fn):
    try:
        fn()
    except BaseException as e:           # noqa: BLE001 - we want the traceback the run would have
        return e
    raise AssertionError("expected an exception")


def test_an_error_raised_by_the_strategy_file_is_the_strategys_fault_and_names_the_line(tmp_path):
    f = tmp_path / "broken.py"
    f.write_text(BROKEN)
    exc = raised(lambda: _run_in_file(f))
    o = outcome.from_exception(exc, str(f))
    assert o.kind == "strategy_error" and o.code == "BT-RUN-001"
    assert o.line == 11 and o.source == "broken.py"
    assert "line 11" in o.message and "1 / 0" in o.message
    assert "in the strategy file" in o.action


def _run_in_file(path: Path):
    code = compile(path.read_text(), str(path), "exec")
    g = {}
    exec(code, g)
    g["Broken"]().on_bar(_Ctx())


class _Ctx:
    def closes(self, *a):
        return np.array([1.0])


def test_a_coded_error_is_a_settings_problem_with_its_own_code():
    o = outcome.from_exception(CodedError("the start date is after the last available bar", code="BT-RUN-002"), None)
    assert o.kind == "input_error" and o.code == "BT-RUN-002" and "start date" in o.message


def test_missing_data_is_a_settings_problem_that_says_what_to_download():
    o = outcome.from_exception(DataError("no cached bars for XYZ"), None)
    assert o.kind == "input_error" and o.code == "BT-DATA-000" and "Download" in o.action


def test_an_internal_error_is_not_blamed_on_the_strategy():
    o = outcome.from_exception(KeyError("column"), "strategies/examples/sma_cross.py")
    assert o.kind == "analysis_error" and o.code == "BT-RUN-003"
    assert "did not raise" in o.message


@pytest.mark.parametrize("metrics, level", [
    ({"total_return": 0.1, "benchmark_total_return": 0.2, "trades": 4}, "lagged"),
    ({"total_return": -0.05, "benchmark_total_return": 0.2, "trades": 4}, "loss"),
    ({"total_return": 0.3, "benchmark_total_return": 0.2, "trades": 4}, "beat"),
    ({"total_return": 0.3, "benchmark_total_return": None, "trades": 4}, "profit"),
    ({"total_return": 0.0, "benchmark_total_return": 0.2, "trades": 0}, "none"),
    ({"benchmark_total_return": 0.2, "trades": 4}, None),
    (None, None),
])
def test_the_verdict_describes_the_strategy_result_not_the_run(metrics, level):
    v = outcome.verdict(metrics)
    assert (v or {}).get("level") == level


def test_emit_prints_a_readable_block_and_a_parseable_marker(capsys):
    with pytest.raises(SystemExit) as e:
        outcome.emit(outcome.failure("input_error", "no data", "download it", code="BT-RUN-002"))
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "RESULT: The settings cannot be used [BT-RUN-002]" in out and "What to do: download it" in out
    marker = [ln for ln in out.splitlines() if ln.startswith(outcome.MARKER)][-1]
    assert json.loads(marker[len(outcome.MARKER):])["kind"] == "input_error"


def test_the_cli_reports_a_strategy_bug_with_a_marker_and_a_failed_exit(tmp_path, capsys):
    cache_dir, runs = tmp_path / "cache", tmp_path / "runs"
    n = 80
    closes = 100 + np.arange(n, dtype=float)
    times = pd.date_range("2023-01-03 14:30", periods=n, freq="B", tz="UTC")
    payload = {"chart_step": 86400, "time": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in times],
               "open": closes.tolist(), "close": closes.tolist(), "high": closes.tolist(), "low": closes.tolist(),
               "volume": [1000] * n}
    f = tmp_path / "spy.json"
    f.write_text(json.dumps(payload))
    cli.main(["--cache", str(cache_dir), "ingest-ibkr", "SPY", str(f)])
    strat = tmp_path / "broken.py"
    strat.write_text(BROKEN)
    with pytest.raises(SystemExit) as e:
        cli.main(["--cache", str(cache_dir), "run", str(strat), "--out", str(runs), "--costs", str(tmp_path / "none.toml")])
    assert e.value.code == 1
    captured = capsys.readouterr()
    out = captured.out
    marker = [ln for ln in out.splitlines() if ln.startswith(outcome.MARKER)][-1]
    got = json.loads(marker[len(outcome.MARKER):])
    assert got["kind"] == "strategy_error" and got["code"] == "BT-RUN-001" and got["line"] == 11
    assert "ZeroDivisionError" in captured.err   # the traceback is kept for the technical details


# --- the dashboard's view of a finished job ---

def _job(tmp_path, code, text, run_id=None, metrics=None):
    jdir = tmp_path / "runs" / "_jobs"
    jdir.mkdir(parents=True)
    jid = "abcdef012345"
    (jdir / f"{jid}.log").write_text(text, encoding="utf-8")
    job = {"id": jid, "started": 0, "status": "running", "strategy": "strategies/x.py", "run_id": run_id}
    (jdir / f"{jid}.json").write_text(json.dumps(job))
    if run_id:
        (tmp_path / "runs" / run_id).mkdir(parents=True)
        (tmp_path / "runs" / run_id / "metrics.json").write_text(json.dumps(metrics or {}))
    return jobs.Jobs(tmp_path, tmp_path / "runs", tmp_path / "cache"), jid


def test_a_strategy_error_job_shows_the_strategy_status_and_the_line(tmp_path):
    marker = outcome.MARKER + json.dumps(outcome.failure("strategy_error", "ZeroDivisionError: x (broken.py, line 11).",
                                                          "fix it", line=11).as_dict())
    j, jid = _job(tmp_path, 1, "traceback...\n" + marker + "\n")
    class Done:
        def poll(self): return 1
    j.procs[jid] = Done()
    s = j.status(jid)
    assert s["status"] == "strategy_error" and s["code"] == "BT-RUN-001" and s["line"] == 11


def test_a_finished_run_with_a_loss_is_done_and_says_the_strategy_lost(tmp_path):
    j, jid = _job(tmp_path, 0, "Saved to /x/runs/20260102-000000-Trend\n", run_id="20260102-000000-Trend",
                  metrics={"total_return": -0.1, "benchmark_total_return": 0.2, "trades": 3})
    class Done:
        def poll(self): return 0
    j.procs[jid] = Done()
    s = j.status(jid)
    assert s["status"] == "done" and s["kind"] == "ok" and s["verdict"]["level"] == "loss"


def test_a_job_that_exits_without_a_reason_is_an_analysis_error_not_a_strategy_error(tmp_path):
    j, jid = _job(tmp_path, 3, "some output\n")
    class Done:
        def poll(self): return 3
    j.procs[jid] = Done()
    s = j.status(jid)
    assert s["status"] == "analysis_error" and s["code"] == "BT-RUN-003"


def test_a_job_that_runs_past_the_limit_is_stopped(tmp_path):
    j, jid = _job(tmp_path, 0, "")
    j.procs.pop(jid, None)
    job = json.loads((j.dir / f"{jid}.json").read_text())
    job["started"] = 0
    (j.dir / f"{jid}.json").write_text(json.dumps(job))
    s = j.status(jid)
    assert s["status"] == "stopped" and s["code"] == "BT-RUN-004"
