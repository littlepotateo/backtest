"""Claude describes a strategy (and, against a paper, grounds its edge in that paper). The description is saved as data; the
strategy file is never changed, and a reply that does not validate saves nothing."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backtester import claude_code
from backtester.claude_code import ClaudeError
from backtester.research import Library
from backtester.research import claude_jobs
from backtester.web import strategies as S
from backtester.web import strategy_store as store
from backtester.web.app import create_app

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def project(tmp_path):
    (tmp_path / "strategies" / "examples").mkdir(parents=True)
    shutil.copy(ROOT / "strategies" / "examples" / "sma_cross.py", tmp_path / "strategies" / "examples" / "sma_cross.py")
    return tmp_path


def fake_claude(monkeypatch, reply, seen=None):
    def run(prompt, *, allowed_tools, cwd, log=None, **k):
        if seen is not None:
            seen.update(prompt=prompt, allowed_tools=allowed_tools)
        return {"text": json.dumps(reply), "denied": []}
    monkeypatch.setattr(claude_jobs, "run_claude", run)


def test_a_description_is_saved_as_data_and_the_strategy_file_is_untouched(project, monkeypatch):
    before = (project / "strategies" / "examples" / "sma_cross.py").read_bytes()
    fake_claude(monkeypatch, {"description": "Holds SPY while its fast average is above the slow one.",
                              "edge": "Trends persist.", "assumptions": ["Daily bars."], "risks": ["Whipsaw in sideways markets."]})
    out = claude_jobs.describe_job(project, "strategies/examples/sma_cross.py", None, project / "research" / "library", lambda s: None)
    assert out["path"] == "strategies/examples/sma_cross.py"
    assert (project / "strategies" / "examples" / "sma_cross.py").read_bytes() == before
    assert not list((project / "strategies").rglob("*.meta.json"))              # no sidecar is written next to shipped code
    saved = store.load_descriptions(project)["strategies/examples/sma_cross.py"]
    assert saved["description"].startswith("Holds SPY") and saved["risks"] == ["Whipsaw in sideways markets."]
    listed = {s["name"]: s for s in S.list_strategies(project)}["SmaCross"]
    assert listed["ai_description"].startswith("Holds SPY") and listed["ai_edge"] == "Trends persist." and listed["ai_described"]


def test_against_a_paper_the_prompt_carries_its_claims_and_claude_reads_nothing_else(project, monkeypatch):
    lib = Library(project / "research" / "library")
    pid = lib.add("Trend timing in equities", authors="A. Author", year=2020)
    lib.set_analysis(pid, {"summary": "s", "rules": [], "claimed_results": ["Sharpe 0.9"], "assumptions_needed": [],
                           "missing_information": [], "replication_difficulty": "easy", "can_backtest_here": "yes",
                           "suggested_strategy_description": ""}, from_full_text=False)
    seen = {}
    fake_claude(monkeypatch, {"description": "d", "edge": "Persistence, as the paper argues."}, seen)
    claude_jobs.describe_job(project, "strategies/examples/sma_cross.py", pid, project / "research" / "library", lambda s: None)
    assert "Trend timing in equities" in seen["prompt"] and "Sharpe 0.9" in seen["prompt"]
    assert seen["allowed_tools"] == ["Read(./__none__)"]
    assert store.load_descriptions(project)["strategies/examples/sma_cross.py"]["paper"] == pid


def test_a_reply_without_a_description_saves_nothing(project, monkeypatch):
    fake_claude(monkeypatch, {"edge": "something"})
    with pytest.raises(ClaudeError, match="no description"):
        claude_jobs.describe_job(project, "strategies/examples/sma_cross.py", None, project / "research" / "library", lambda s: None)
    assert store.load_descriptions(project) == {}


@pytest.mark.parametrize("rel", ["../outside.py", "strategies/examples/missing.py", "strategies/examples/sma_cross.txt"])
def test_only_strategy_files_in_the_strategies_folder_can_be_described(project, rel):
    with pytest.raises(Exception, match="not a strategy file"):
        store.strategy_file(project, rel)


def test_removed_strategies_are_not_described(project):
    (project / "strategies" / "removed").mkdir()
    shutil.copy(project / "strategies" / "examples" / "sma_cross.py", project / "strategies" / "removed" / "old.py")
    with pytest.raises(Exception, match="not available to run"):
        store.strategy_file(project, "strategies/removed/old.py")


def test_the_route_refuses_a_bad_path_and_says_when_claude_is_missing(project, monkeypatch):
    client = TestClient(create_app(project), raise_server_exceptions=False)
    r = client.post("/api/strategies/describe", json={"path": "../etc/passwd"})
    assert r.status_code == 400 and r.json()["code"] == "BT-RUN-002"
    monkeypatch.setattr(claude_code, "find_claude", lambda: None)
    r = client.post("/api/strategies/describe", json={"path": "strategies/examples/sma_cross.py"})
    assert r.json()["code"] == "BT-CLAUDE-001"
