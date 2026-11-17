"""One unreadable file in the user's folders must not turn the whole dashboard into 'Internal Server Error'."""

import json

import pytest
from fastapi.testclient import TestClient

from backtester.web import app as app_mod
from backtester.web.app import create_app

PAGES = ["/", "/new", "/runs", "/data", "/research", "/compare", "/research/library", "/research/requests"]


def serve(root):
    return TestClient(create_app(root), raise_server_exceptions=False)


def all_ok(c):
    bad = {p: c.get(p).status_code for p in PAGES if c.get(p).status_code != 200}
    assert not bad, bad


def test_a_page_error_shows_the_reason_not_a_bare_internal_server_error(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod.service, "dataset_table", lambda cache: (_ for _ in ()).throw(KeyError("end")))
    r = serve(tmp_path).get("/")
    assert r.status_code == 500 and "text/html" in r.headers["content-type"]
    assert "BT-HTTP-500" in r.text and "KeyError" in r.text and "dataset_table" in r.text and "start.sh" in r.text



def test_unreadable_cache_metadata_is_skipped(tmp_path):
    cache = tmp_path / "data" / "cache"
    (cache / "SPY").mkdir(parents=True)
    (cache / "SPY" / "1d.json").write_text("{not json")
    (cache / "QQQ").mkdir()
    (cache / "QQQ" / "1d.json").write_text(json.dumps({"symbol": "QQQ", "interval": "1d"}))     # no start or end
    all_ok(serve(tmp_path))


def test_odd_strategy_files_are_skipped_not_fatal(tmp_path):
    folder = tmp_path / "strategies" / "mine"
    folder.mkdir(parents=True)
    (folder / "nul.py").write_bytes(b"x = 1\x00\n")
    (folder / "bad_bytes.py").write_bytes(b"\xff\xfe\x00 class")
    (folder / "weird.py").write_text('from backtester import Strategy\nclass A(Strategy):\n    universe = 5\n    interval = 3\n    params = "x"\n'
                                     '    options_on = {"a": 1}\n    param_grid = [1]\n')
    (folder / "string_universe.py").write_text('from backtester import Strategy\nclass B(Strategy):\n    universe = "SPY"\n')
    c = serve(tmp_path)
    all_ok(c)
    names = {s["name"]: s for s in c.get("/api/strategies").json()["strategies"]}
    assert names["B"]["universe"] == ["SPY"] and names["A"]["universe"] == [] and names["A"]["interval"] == "1d"


@pytest.mark.parametrize("content", ["{}", "[]", "{\"papers\": null}", "{\"papers\": {\"x\": {}}}"])
def test_odd_library_index_does_not_break_pages(tmp_path, content):
    lib = tmp_path / "research" / "library"
    lib.mkdir(parents=True)
    (lib / "index.json").write_text(content)
    all_ok(serve(tmp_path))


def test_corrupt_library_index_keeps_home_alive_and_names_the_file(tmp_path):
    lib = tmp_path / "research" / "library"
    lib.mkdir(parents=True)
    (lib / "index.json").write_text("{corrupt")
    c = serve(tmp_path)
    assert c.get("/").status_code == 200 and c.get("/data").status_code == 200
    r = c.get("/research")
    assert r.status_code == 500 and "BT-LIB-001" in r.text and "index.json" in r.text


def test_garbage_in_requests_and_runs_folders(tmp_path):
    reqs = tmp_path / "research" / "library" / "requests"
    reqs.mkdir(parents=True)
    (reqs / "20260101-000000-abcd.json").write_text("{half")
    (reqs / "20260101-000001-abcd.json").write_text("[]")
    (reqs / "20260101-000002-abcd.json").write_text(json.dumps({"id": "20260101-000002-abcd", "query": "ok", "status": "pending", "papers": [], "notes": ""}))
    run = tmp_path / "runs" / "20260101-000000-X"
    run.mkdir(parents=True)
    (run / "meta.json").write_text("{nope")
    (run / "metrics.json").write_text("{}")
    c = serve(tmp_path)
    all_ok(c)
    assert "ok" in c.get("/research/requests").text
