"""The results page keeps data notes apart from findings, merges skipped tests, lists recent runs with their outcome,
and shows a form error with a code and what to do."""

import json

from fastapi.testclient import TestClient

from backtester.analysis.findings import flags
from backtester.web import jobs as J
from backtester.web.app import create_app


def test_data_notes_are_not_findings_and_skipped_tests_share_one_line():
    v = {"metrics": {"trades": 50, "total_return": 0.1, "benchmark_total_return": 0.2},
         "checks": {"lookahead": {"passed": True, "same_bar_fills": False},
                    "data": {"SPY": {"issues": ["1 bar(s) moved more than 10 standard deviations"]}},
                    "trades": {"trades": 50}},
         "skipped": {"walkforward": "needs more history", "sensitivity": "needs more history", "kelly": "no grid"}}
    f = flags(v)
    notes = [x for x in f if x.get("kind") == "data_note"]
    assert notes and all(x["test"] == "data" for x in notes)
    assert all(x.get("kind", "finding") == "finding" for x in f if x not in notes and x.get("kind") != "note")
    skipped = [x for x in f if x.get("kind") == "note"]
    assert len(skipped) == 2                                                  # the two with the same reason become one line
    assert any("walkforward, sensitivity" in x["test"] and "needs more history" in x["message"] for x in skipped)


def test_recent_jobs_are_listed_newest_first_with_their_outcome(tmp_path):
    jdir = tmp_path / "runs" / "_jobs"
    jdir.mkdir(parents=True)
    for jid, started, status, code in (("aaaaaaaaaaaa", 100, "failed", None), ("bbbbbbbbbbbb", 200, "done", None)):
        (jdir / f"{jid}.json").write_text(json.dumps({"id": jid, "started": started, "status": status, "strategy": "x.py",
                                                       "title": "Run completed" if status == "done" else "Error completing the analysis",
                                                       "code": code, "run_id": None}))
        (jdir / f"{jid}.log").write_text("")
    j = J.Jobs(tmp_path, tmp_path / "runs", tmp_path / "cache")
    rows = j.recent()
    assert [r["id"] for r in rows] == ["bbbbbbbbbbbb", "aaaaaaaaaaaa"]


def test_a_form_error_says_what_to_do_and_gives_a_code(tmp_path):
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)
    r = client.post("/rerun", data={"strategy": "../x.py"})
    assert r.status_code == 400
    assert "BT-RUN-002" in r.text and "What to do" in r.text


def test_the_job_page_has_a_copy_button_and_the_technical_details_collapsed(tmp_path):
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)
    jdir = tmp_path / "runs" / "_jobs"
    jdir.mkdir(parents=True)
    jid = "cccccccccccc"
    (jdir / f"{jid}.json").write_text(json.dumps({"id": jid, "started": 1, "status": "strategy_error", "strategy": "s.py",
                                                   "title": "Your strategy stopped with an error", "code": "BT-RUN-001",
                                                   "message": "ZeroDivisionError", "action": "fix it", "kind": "strategy_error"}))
    (jdir / f"{jid}.log").write_text("Traceback...\n")
    r = client.get(f"/jobs/{jid}")
    assert "Strategy failed: the strategy" in r.text and "BT-RUN-001" in r.text
    assert 'id="copy-details"' in r.text and "<details" in r.text


def test_an_impossible_date_is_refused_as_a_settings_problem_before_the_run_starts(tmp_path):
    import pytest
    from backtester.web.jobs import BadRequest, Jobs
    (tmp_path / "strategies").mkdir()
    (tmp_path / "strategies" / "x.py").write_text("")
    j = Jobs(tmp_path, tmp_path / "runs", tmp_path / "cache")
    with pytest.raises(BadRequest, match="real date"):
        j.command({"strategy": "strategies/x.py", "start": "2020-13-45"})
    assert j.command({"strategy": "strategies/x.py", "start": "2020-02-29"})   # 2020 is a leap year
