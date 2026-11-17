"""Every error the dashboard shows carries a short code, and a missing feature says why instead of just 'Not Found'."""

import re
import sys

import pytest
from fastapi.testclient import TestClient

from backtester.data.yahoo import DataError
from backtester.errors import CODE_PATTERN
from backtester.research import Library
from backtester.research.ingest import PaperError, read_pdf
from backtester.web.app import create_app
from backtester.web.tasks import Tasks
from tests.test_web_stage8 import PAPER, pdf_bytes


@pytest.fixture
def project(tmp_path):
    return tmp_path


@pytest.fixture
def client(project):
    return TestClient(create_app(project), raise_server_exceptions=False)


def test_a_missing_route_explains_a_stale_server_and_gives_a_code(client):
    r = client.post("/api/papers/no-such-feature")
    j = r.json()
    assert r.status_code == 404 and j["code"] == "BT-HTTP-404" and j["error"] != "Not Found"
    assert "older version" in j["error"] and "POST /api/papers/no-such-feature" in j["error"] and "version" in j


def test_wrong_method_and_cross_site_posts_have_codes(client):
    r = client.get("/api/papers/upload")                      # the route exists, but only for POST
    assert r.status_code == 405 and r.json()["code"] == "BT-HTTP-405"
    r = client.post("/api/requests", json={"query": "momentum"}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "BT-HTTP-403"


def test_unexpected_errors_have_a_code(client, monkeypatch):
    monkeypatch.setattr("backtester.web.routes.search_papers", lambda q: (_ for _ in ()).throw(RuntimeError("x")))
    j = client.get("/api/papers/search?q=momentum").json()
    assert j["code"] == "BT-HTTP-500" and "RuntimeError" in j["error"]


def test_upload_failures_carry_codes_per_file(client):
    res = client.post("/api/papers/upload", files=[("files", ("notes.txt", b"hi", "text/plain")),
                                                   ("files", ("broken.pdf", b"%PDF-1.4 nope", "application/pdf")),
                                                   ("files", ("fake.pdf", b"hello", "application/pdf"))]).json()["results"]
    assert [r["code"] for r in res] == ["BT-PDF-006", "BT-PDF-005", "BT-PDF-002"]
    assert client.post("/api/papers/upload", files=[]).json()["code"] == "BT-PDF-007"


def test_pdf_error_codes(monkeypatch):
    with pytest.raises(PaperError) as e:
        read_pdf(b"x" * 10, "a.pdf")
    assert e.value.code == "BT-PDF-002"
    monkeypatch.setitem(sys.modules, "pypdf", None)
    with pytest.raises(PaperError) as e:
        read_pdf(PAPER, "a.pdf")
    assert e.value.code == "BT-PDF-003"


def test_search_errors_have_codes(client):
    j = client.get("/api/papers/search?q=ab").json()
    assert j["code"] == "BT-SRCH-001" and "three" in j["error"]
    j = client.post("/api/requests", json={"query": "x"}).json()
    assert j["code"] == "BT-REQ-001"


def test_data_errors_and_task_errors_have_codes(client):
    j = client.post("/api/data/fetch", json={"symbols": "", "interval": "1d"}).json()
    assert re.match(CODE_PATTERN, j["code"]), j
    tasks = Tasks()
    tid = tasks.submit("t", lambda log: (_ for _ in ()).throw(DataError("nope", code="BT-NET-429")))
    import time
    for _ in range(50):
        t = tasks.get(tid)
        if t["status"] != "running":
            break
        time.sleep(0.05)
    assert t["error"] == "nope" and t["code"] == "BT-NET-429"


def test_every_code_in_the_source_is_documented():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    used = set()
    for f in list((root / "backtester").rglob("*.py")) + list((root / "backtester").rglob("*.js")):
        used |= set(re.findall(r"BT-[A-Z]+-\d{3}", f.read_text()))
    doc = (root / "docs" / "error-codes.md").read_text()
    missing = sorted(c for c in used if c not in doc)
    assert not missing, f"codes used but not documented: {missing}"


# --- ids for papers ---------------------------------------------------------------------------
def test_a_title_without_latin_letters_still_gets_a_usable_id(client, project):
    from backtester.research.library import slug
    for title, year in (("动量策略研究", 2019), ("!!! ???", None), ("Моментум", 2020), ("2019", 2019)):
        s = slug(title, year)
        assert re.match(r"^[a-z0-9][a-z0-9-]{0,120}$", s), (title, s)
    assert slug("动量策略研究", 2019) != slug("价值投资研究", 2019)        # different titles never collide
    res = client.post("/api/papers/upload", files=[("files", ("a.pdf", pdf_bytes(["!!! ??? ### $$$ %%% &&& ***"]), "application/pdf"))]).json()["results"][0]
    pid = res["id"]
    assert pid and client.get(f"/research/file/{pid}.pdf").status_code == 200
    assert client.post(f"/api/papers/{pid}/delete").json() == {"ok": True}


def test_papers_saved_with_a_broken_id_are_repaired_on_load(project):
    import json
    root = project / "research" / "library"
    (root / "files").mkdir(parents=True)
    (root / "index.json").write_text(json.dumps({"papers": {"-2019": {
        "id": "-2019", "title": "Momentum paper", "authors": "", "year": 2019, "venue": "", "url": "", "consensus_id": "", "finding": "",
        "claims": [], "claims_from_full_text": True, "status": "candidate", "strategies": [], "runs": [], "added": "2026-01-01",
        "pdf": "files/-2019.pdf", "text_file": "files/-2019.txt"}}}))
    (root / "files" / "-2019.pdf").write_bytes(PAPER)
    (root / "files" / "-2019.txt").write_text("text")
    (root / "-2019.md").write_text("# notes")
    papers = Library(root).list()
    assert len(papers) == 1 and re.match(r"^[a-z0-9][a-z0-9-]{0,120}$", papers[0]["id"])
    pid = papers[0]["id"]
    assert (root / "files" / f"{pid}.pdf").read_bytes() == PAPER and (root / f"{pid}.md").exists()
    assert not (root / "files" / "-2019.pdf").exists() and papers[0]["pdf"] == f"files/{pid}.pdf"
    c = TestClient(create_app(project))
    assert c.get(f"/research/file/{pid}.pdf").status_code == 200
