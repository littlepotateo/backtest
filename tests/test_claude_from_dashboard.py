"""The dashboard runs Claude Code itself (`claude -p`): paper analysis after upload, and Consensus search, with no pull request or paste step."""

import json
import stat
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backtester import claude_code, settings
from backtester.claude_code import ClaudeError, extract_json
from backtester.research import Library
from backtester.research.requests import Requests
from backtester.web.app import create_app
from tests.test_web_stage8 import PAPER

FAKE = Path(__file__).parent / "fake_claude.py"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_HOME", str(tmp_path))
    from backtester import paths
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def fake(tmp_path, monkeypatch):
    exe = tmp_path / "bin" / "claude"
    exe.parent.mkdir()
    exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("BACKTEST_CLAUDE", str(exe))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(tmp_path / "calls.log"))
    return exe


@pytest.fixture
def client(project):
    return TestClient(create_app(project), raise_server_exceptions=False)


def wait(client, task_id, seconds=20):
    for _ in range(int(seconds / 0.1)):
        t = client.get(f"/api/tasks/{task_id}").json()
        if t["status"] != "running":
            return t
        time.sleep(0.1)
    raise AssertionError("task did not finish")


def calls(project):
    return [json.loads(x) for x in (project / "calls.log").read_text().splitlines()]


def test_status_reports_whether_claude_code_is_on_this_computer(client, fake, monkeypatch):
    s = client.get("/api/claude/status").json()
    assert s["available"] is True and s["path"] == str(fake)
    monkeypatch.setenv("BACKTEST_CLAUDE", "/nonexistent/claude")
    s = client.get("/api/claude/status").json()
    assert s["available"] is False and "code.claude.com" in s["help"]


def test_extract_json_handles_fences_and_chatter():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Here:\n```json\n{"a": {"b": "}"}}\n```\nthanks') == {"a": {"b": "}"}}
    with pytest.raises(ClaudeError) as e:
        extract_json("no json here")
    assert e.value.code == "BT-CLAUDE-005"


def test_uploaded_paper_is_analysed_and_saved(client, fake, project):
    up = client.post("/api/papers/upload", files=[("files", ("m.pdf", PAPER, "application/pdf"))]).json()["results"][0]
    pid = up["id"]
    t = wait(client, client.post(f"/api/papers/{pid}/analyse").json()["task_id"])
    assert t["status"] == "done", t
    p = Library(project / "research" / "library").get(pid)
    assert p["analysis"]["strategy_family"] == "trend following" and p["analysis"]["replication_difficulty"] == "easy"
    assert p["claims"] == ["Timing cut drawdowns to under 10%"] and p["claims_from_full_text"] is True
    assert "10-month moving average" in (project / "research" / "library" / f"{pid}.md").read_text(encoding="utf-8")
    page = client.get("/research/library").text
    assert "Claude's analysis (" in page and "Hold the asset when price is above its 10-month average" in page and "Analyse again with Claude" in page
    # Claude gets only a read permission for that one file, no shell, no writing, and the prompt comes on stdin
    args = calls(project)[0]["args"]
    allowed = args[args.index("--allowedTools") + 1:]
    assert allowed == [f"Read(./research/library/files/{pid}.txt)"]
    assert "--permission-mode" in args and args[args.index("--permission-mode") + 1] == "dontAsk" and "Bash" not in " ".join(args)


def test_analysis_never_overwrites_claims_the_user_typed(client, fake, project):
    lib = Library(project / "research" / "library")
    pid = lib.add("Typed Paper", year=2020, finding="abstract text here", claims=["my own note"])
    t = wait(client, client.post(f"/api/papers/{pid}/analyse").json()["task_id"])
    assert t["status"] == "done"
    p = lib.get(pid)
    assert p["claims"] == ["my own note"] and p["analysis"]["claimed_results"] == ["Timing cut drawdowns to under 10%"]
    assert p["claims_from_full_text"] is False and p["analysis"]["from_full_text"] is False        # abstract only


def test_a_paper_with_nothing_to_read_is_refused_with_a_code(client, fake, project):
    pid = Library(project / "research" / "library").add("Empty", year=2020)
    t = wait(client, client.post(f"/api/papers/{pid}/analyse").json()["task_id"])
    assert t["status"] == "failed" and t["code"] == "BT-CLAUDE-005" and "Drop its PDF" in t["error"]


def test_search_saves_papers_and_finishes_the_request(client, fake, project):
    made = client.post("/api/claude/search", json={"query": "trend following", "notes": "after 2010"}).json()
    assert made["claude"] is True
    t = wait(client, made["task_id"])
    assert t["status"] == "done", t
    lib = Library(project / "research" / "library")
    titles = {p["title"]: p for p in lib.list()}
    assert set(titles) == {"Trend Following: A Test ﬁlter", "Second paper"}                  # the empty title and the non-object were skipped
    assert titles["Second paper"]["url"] == "" and titles["Second paper"]["year"] == 2019            # a non-https link is dropped
    req = Requests(project / "research" / "library").get(made["request"]["id"])
    assert req["status"] == "done" and len(req["papers"]) == 2 and "Replicate the first" in req["summary"]
    html = client.get("/research/requests").text
    assert "Done" in html and "Second paper" in html
    prompt_args = calls(project)[0]["args"]
    allowed = prompt_args[prompt_args.index("--allowedTools") + 1:]
    assert allowed == ["mcp__Consensus", "mcp__claude_ai_Consensus", "ToolSearch"]


def test_a_connector_named_differently_is_allowed_after_one_denial_and_remembered(client, fake, project, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "denied")
    t = wait(client, client.post("/api/claude/search", json={"query": "trend following"}).json()["task_id"])
    assert t["status"] == "done", t
    assert "mcp__claude_ai_Consensus__search" in settings.get("claude_extra_tools")
    assert len(calls(project)) == 2
    # the next search allows it from the start
    wait(client, client.post("/api/claude/search", json={"query": "momentum"}).json()["task_id"])
    third = calls(project)[2]["args"]
    assert "mcp__claude_ai_Consensus__search" in third[third.index("--allowedTools") + 1:]


@pytest.mark.parametrize("mode,code", [("no_consensus", "BT-CLAUDE-004"), ("auth", "BT-CLAUDE-003"), ("bad_json", "BT-CLAUDE-005"), ("crash", "BT-CLAUDE-002")])
def test_failures_have_codes_and_leave_the_request_waiting(client, fake, project, monkeypatch, mode, code):
    monkeypatch.setenv("FAKE_CLAUDE", mode)
    made = client.post("/api/claude/search", json={"query": "trend following"}).json()
    t = wait(client, made["task_id"])
    assert t["status"] == "failed" and t["code"] == code, t
    assert Requests(project / "research" / "library").get(made["request"]["id"])["status"] == "pending"
    assert Library(project / "research" / "library").list() == []


def test_a_job_that_takes_too_long_is_stopped(client, fake, project, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "slow")
    monkeypatch.setattr(claude_code, "DEFAULT_TIMEOUT", 1)
    t = wait(client, client.post("/api/claude/search", json={"query": "trend following"}).json()["task_id"])
    assert t["status"] == "failed" and t["code"] == "BT-CLAUDE-002" and "stopped" in t["error"]


def test_without_claude_code_the_search_falls_back_to_the_pasted_line(client, project, monkeypatch):
    monkeypatch.setenv("BACKTEST_CLAUDE", "/nonexistent/claude")
    made = client.post("/api/claude/search", json={"query": "trend following"}).json()
    assert made["claude"] is False and "paper-search request" in made["request"]["instruction"] and "code.claude.com" in made["help"]
    r = client.post("/api/papers/x-2020/analyse")
    assert r.status_code == 404                                           # unknown paper
    pid = Library(project / "research" / "library").add("P", year=2020, finding="f")
    r = client.post(f"/api/papers/{pid}/analyse")
    assert r.status_code == 400 and r.json()["code"] == "BT-CLAUDE-001"


def test_invalid_request_text_is_refused_before_anything_runs(client, fake, project):
    r = client.post("/api/claude/search", json={"query": "x"})
    assert r.status_code == 400 and r.json()["code"] == "BT-REQ-001" and not (project / "calls.log").exists()


def test_page_has_the_controls(client):
    html = client.get("/research").text
    assert "auto-analyse" in html and "claude-activity" in html and "claude-status" in html
