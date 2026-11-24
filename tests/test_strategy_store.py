"""The strategy registry: uploaded code is checked, drafts never run until approved, and a removal can be undone by hand."""

import json

import pytest
from fastapi.testclient import TestClient

from backtester.errors import CodedError
from backtester.web import strategies as S
from backtester.web import strategy_store as store
from backtester.web.app import create_app

GOOD = '''"""Buy SPY when it is above its 50-day average."""
from backtester import Strategy


class TrendSpy(Strategy):
    universe = ["SPY"]
    interval = "1d"
    params = {"window": 50}
    param_grid = {"window": [20, 50]}

    def on_bar(self, ctx):
        pass
'''


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / "strategies" / "examples").mkdir(parents=True)
    (tmp_path / "strategies" / "examples" / "shipped.py").write_text(GOOD.replace("TrendSpy", "Shipped"))
    monkeypatch.setattr(store, "dry_run", lambda path, root, cache: {"ok": True, "warning": None})
    return tmp_path


def test_a_valid_file_passes_the_static_checks():
    assert store.check_source(GOOD) == "TrendSpy"


@pytest.mark.parametrize("source, fragment", [
    ("x = 1\n", "exactly one class"),
    (GOOD + "\n\nclass Second(Strategy):\n    universe = ['SPY']\n    interval = '1d'\n", "found 2"),
    (GOOD.replace('    universe = ["SPY"]\n', ''), "must set `universe`"),
    (GOOD.replace('"window": 50', '"window": 50 + 1'), "plain value"),
    ("class Broken(Strategy:\n", "syntax error"),
])
def test_each_structural_problem_is_refused_with_a_reason(source, fragment):
    with pytest.raises(CodedError) as e:
        store.check_source(source)
    assert fragment in str(e.value) and e.value.code == "BT-RUN-002"


def test_upload_needs_the_trust_box_and_a_safe_name(root):
    with pytest.raises(CodedError, match="trust"):
        store.add(root, root / "cache", "trend_spy", GOOD, status="approved", trusted=False)
    with pytest.raises(CodedError, match="letters"):
        store.add(root, root / "cache", "../evil", GOOD, status="approved", trusted=True)
    with pytest.raises(CodedError, match="already exists"):
        store.add(root, root / "cache", "shipped", GOOD, status="approved", trusted=True)


def test_an_added_strategy_lands_in_user_with_its_description(root):
    out = store.add(root, root / "cache", "trend_spy", GOOD, status="approved", trusted=True,
                    description="Trend following", edge="Persistence of trends")
    p = root / out["path"]
    assert p.parent.name == "user" and p.exists()
    meta = json.loads(p.with_suffix(".meta.json").read_text())
    assert meta["description"] == "Trend following" and meta["status"] == "approved"
    listed = {s["name"]: s for s in S.list_strategies(root)}
    assert listed["TrendSpy"]["description"] == "Trend following" and listed["TrendSpy"]["status"] == "approved"


def test_a_failed_dry_run_leaves_nothing_behind(root, monkeypatch):
    def boom(path, root, cache):
        raise CodedError("The strategy raised an error when run: ZeroDivisionError", "BT-RUN-001")
    monkeypatch.setattr(store, "dry_run", boom)
    with pytest.raises(CodedError):
        store.add(root, root / "cache", "bad_one", GOOD, status="approved", trusted=True)
    assert not (root / "strategies" / "user" / "bad_one.py").exists()


def test_drafts_are_listed_for_review_but_never_runnable(root):
    store.add(root, root / "cache", "from_paper", GOOD, status="pending", trusted=True, source_ref="paper-x")
    assert all(s["name"] != "TrendSpy" or "pending" not in s["path"] for s in S.list_strategies(root))
    assert not any("pending" in s["path"] for s in S.list_strategies(root))
    drafts = S.list_pending(root)
    assert len(drafts) == 1 and drafts[0]["source"] == "paper-x" and "class TrendSpy" in drafts[0]["code"]


def test_approve_moves_the_draft_into_user_and_nothing_else_runs(root):
    out = store.add(root, root / "cache", "from_paper", GOOD, status="pending", trusted=True)
    new_path = store.approve(root, out["path"], root / "cache")
    assert new_path.startswith("strategies/user/") and (root / new_path).exists()
    assert not (root / out["path"]).exists()
    assert json.loads((root / new_path).with_suffix(".meta.json").read_text())["status"] == "approved"


def test_reject_deletes_only_the_draft(root):
    out = store.add(root, root / "cache", "from_paper", GOOD, status="pending", trusted=True)
    store.reject(root, out["path"])
    assert not (root / out["path"]).exists() and (root / "strategies" / "examples" / "shipped.py").exists()


def test_remove_moves_to_removed_and_refuses_shipped_files(root):
    out = store.add(root, root / "cache", "trend_spy", GOOD, status="approved", trusted=True)
    moved = store.remove(root, out["path"])
    assert moved.startswith("strategies/removed/") and (root / moved).exists()
    assert not (root / out["path"]).exists()
    with pytest.raises(CodedError, match="cannot be changed"):
        store.remove(root, "strategies/examples/shipped.py")


def test_the_upload_route_checks_and_stores_a_file(root, monkeypatch):
    client = TestClient(create_app(root), raise_server_exceptions=False)
    r = client.post("/api/strategies/upload",
                    files={"file": ("trend_spy.py", GOOD.encode(), "text/x-python")},
                    data={"name": "trend_spy", "description": "Trend", "trusted": "on"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    r = client.post("/api/strategies/upload", files={"file": ("notes.txt", b"hi", "text/plain")}, data={"trusted": "on"})
    assert r.status_code == 400 and r.json()["code"] == "BT-RUN-002"
    assert client.get("/strategies").status_code == 200


def test_the_strategies_page_shows_a_draft_for_review(root):
    store.add(root, root / "cache", "from_paper", GOOD, status="pending", trusted=True, description="Draft trend", edge="Trends persist",
              source_ref="paper-x")
    client = TestClient(create_app(root), raise_server_exceptions=False)
    r = client.get("/strategies")
    assert r.status_code == 200
    assert "Drafts waiting for your review" in r.text and "Approve" in r.text and "Edge:" in r.text and "Draft trend" in r.text
    assert 'data-action="approve"' in r.text and "paper-x" in r.text


def test_a_draft_is_not_run_until_approved_and_a_failing_one_stays_pending(root, monkeypatch):
    calls = []
    def boom(path, root, cache):
        calls.append(path.name)
        raise CodedError("The strategy raised an error when run: ZeroDivisionError", "BT-RUN-001")
    out = store.add(root, root / "cache", "from_paper", GOOD, status="pending", trusted=True, dry_run_now=False)
    assert calls == []                                              # creating a draft runs nothing
    monkeypatch.setattr(store, "dry_run", boom)
    with pytest.raises(CodedError, match="ZeroDivisionError"):
        store.approve(root, out["path"], root / "cache")
    assert calls == ["from_paper.py"] and (root / out["path"]).exists()   # refused, still in the queue
