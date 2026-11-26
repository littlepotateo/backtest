"""A strategy drafted by Claude from a paper goes to the review queue, is checked for structure, and is not run until approved."""

import json

import pytest

from backtester.claude_code import ClaudeError
from backtester.research import Library
from backtester.research import claude_jobs
from backtester.web import strategy_store as store

GOOD_CODE = '''from backtester import Strategy


class TrendPaper(Strategy):
    """Trend timing from the paper."""
    universe = ["SPY"]
    interval = "1d"
    params = {"lookback": 12}

    def on_bar(self, ctx):
        ctx.closes("SPY", self.params["lookback"])
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "strategies").mkdir()
    monkeypatch.setattr(store, "dry_run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a draft must not run")))
    return tmp_path


def paper(project, analysed=True):
    lib_dir = project / "research" / "library"
    lib = Library(lib_dir)
    pid = lib.add("Trend timing in equities", authors="A. Author", year=2020)
    if analysed:
        lib.set_analysis(pid, {"summary": "Trends persist.", "rules": ["Hold SPY when the 12-month return is positive."],
                               "claimed_results": [], "assumptions_needed": [], "missing_information": [],
                               "replication_difficulty": "easy", "can_backtest_here": "yes", "suggested_strategy_description": ""},
                         from_full_text=False)
    return lib_dir, pid


def fake_claude(monkeypatch, reply: dict, seen: dict | None = None):
    def run(prompt, *, allowed_tools, cwd, log=None, **k):
        if seen is not None:
            seen.update(prompt=prompt, allowed_tools=allowed_tools)
        return {"text": json.dumps(reply), "denied": []}
    monkeypatch.setattr(claude_jobs, "run_claude", run)


def test_a_draft_goes_to_the_queue_with_its_source_and_assumptions_and_is_not_run(project, monkeypatch):
    lib_dir, pid = paper(project)
    seen = {}
    fake_claude(monkeypatch, {"can_draft": True, "name": "trend_paper", "description": "Hold when trending.",
                              "edge": "Trends persist.", "assumptions": ["SPY stands in for the index."], "code": GOOD_CODE}, seen)
    out = claude_jobs.draft_job(lib_dir, project, project / "data" / "cache", pid, lambda s: None)
    assert out["drafted"] is True and out["path"] == "strategies/pending/trend_paper.py"
    meta = json.loads((project / "strategies" / "pending" / "trend_paper.meta.json").read_text())
    assert meta["source"] == pid and meta["status"] == "pending" and meta["assumptions"] == ["SPY stands in for the index."]
    assert "Hold SPY when the 12-month return is positive." in seen["prompt"]      # the analysed rules are the brief
    assert seen["allowed_tools"] == ["Read(./__none__)"]                       # no full text here: Claude may read nothing


def test_a_paper_that_cannot_be_drafted_saves_nothing(project, monkeypatch):
    lib_dir, pid = paper(project)
    fake_claude(monkeypatch, {"can_draft": False, "reason": "It needs futures contracts this tool does not trade."})
    out = claude_jobs.draft_job(lib_dir, project, project / "data" / "cache", pid, lambda s: None)
    assert out == {"drafted": False, "reason": "It needs futures contracts this tool does not trade."}
    assert not (project / "strategies" / "pending").exists()


def test_a_draft_that_fails_the_structure_check_is_refused_with_a_code(project, monkeypatch):
    lib_dir, pid = paper(project)
    fake_claude(monkeypatch, {"can_draft": True, "name": "broken_one", "code": "class Broken(Strategy:\n"})
    with pytest.raises(ClaudeError, match="structure check") as e:
        claude_jobs.draft_job(lib_dir, project, project / "data" / "cache", pid, lambda s: None)
    assert e.value.code == "BT-RUN-002" and not any((project / "strategies").rglob("broken_one.py"))


def test_a_name_clash_gets_a_number_and_a_bad_name_falls_back_to_the_title(project, monkeypatch):
    lib_dir, pid = paper(project)
    fake_claude(monkeypatch, {"can_draft": True, "name": "Trend Paper!", "code": GOOD_CODE})
    first = claude_jobs.draft_job(lib_dir, project, project / "data" / "cache", pid, lambda s: None)
    assert first["name"] == "trend_paper"
    fake_claude(monkeypatch, {"can_draft": True, "name": "trend_paper", "code": GOOD_CODE})
    second = claude_jobs.draft_job(lib_dir, project, project / "data" / "cache", pid, lambda s: None)
    assert second["name"] == "trend_paper_2"


def test_a_paper_without_an_analysis_is_not_drafted(project, monkeypatch):
    lib_dir, pid = paper(project, analysed=False)
    fake_claude(monkeypatch, {"can_draft": True, "code": GOOD_CODE})
    with pytest.raises(ClaudeError, match="Analyse the paper"):
        claude_jobs.draft_job(lib_dir, project, project / "data" / "cache", pid, lambda s: None)


def test_code_wrapped_in_a_markdown_fence_is_still_drafted(project, monkeypatch):
    """Claude often fences code inside the JSON string; the fence is not Python and used to fail the structure check."""
    lib_dir, pid = paper(project)
    fake_claude(monkeypatch, {"can_draft": True, "name": "trend_paper", "code": "```python\n" + GOOD_CODE + "```"})
    out = claude_jobs.draft_job(lib_dir, project, project / "data" / "cache", pid, lambda s: None)
    assert out["drafted"] is True and (project / "strategies" / "pending" / "trend_paper.py").read_text().startswith("from backtester")


def test_fence_with_prose_before_it_is_unwrapped(project, monkeypatch):
    lib_dir, pid = paper(project)
    fake_claude(monkeypatch, {"can_draft": True, "name": "trend_paper",
                              "code": "Here is the strategy:\n```python\n" + GOOD_CODE + "```\nLet me know."})
    out = claude_jobs.draft_job(lib_dir, project, project / "data" / "cache", pid, lambda s: None)
    assert out["drafted"] is True
    assert "Let me know" not in (project / "strategies" / "pending" / "trend_paper.py").read_text()
