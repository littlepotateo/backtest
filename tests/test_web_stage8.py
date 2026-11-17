"""Browser-only workflow: background tasks, data and paper endpoints, strategy discovery, launchers."""

import json
import os
import subprocess
import time
import urllib.error
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backtester.data import service
from backtester.data.cache import Cache
from backtester.data.yahoo import DataError
from backtester.research import Library
from backtester.research import search as search_mod
from backtester.research.ingest import PaperError, read_pdf
from backtester.web import strategies as S
from backtester.web.app import create_app
from backtester.web.tasks import Tasks

ROOT = Path(__file__).resolve().parent.parent


def pdf_bytes(lines: list[str]) -> bytes:
    """A small valid one-page PDF whose text is `lines`."""
    text = "BT /F1 11 Tf 14 TL 72 740 Td " + " ".join(f"({ln.replace('(', '[').replace(')', ']')}) Tj T*" for ln in lines) + " ET"
    objs = ["<</Type/Catalog/Pages 2 0 R>>", "<</Type/Pages/Kids[3 0 R]/Count 1>>",
            "<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
            f"<</Length {len(text)}>>\nstream\n{text}\nendstream", "<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    return out + f"trailer\n<</Root 1 0 R/Size {len(objs) + 1}>>\nstartxref\n{xref}\n%%EOF\n".encode()


PAPER = pdf_bytes(["Momentum Strategies in Equity Markets", "J. Doe and A. Roe", "Published 2019",
                   "Abstract", "We study a simple momentum rule applied to large capitalisation stocks over a thirty year sample.",
                   "The rule buys recent winners and sells recent losers each month, and we find that returns persist after costs",
                   "for about a year before fading, with the strongest effect in the smallest firms of the sample studied here.", "",
                   "Keywords: momentum, anomalies", "1. Introduction", "Text of the paper continues here."])


def fake_bars(n=40, start="2024-01-02 14:30"):
    idx = pd.date_range(start, periods=n, freq="B", tz="UTC")
    c = 100 + np.arange(n, dtype=float)
    return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1000.0, "adj_factor": 1.0}, index=idx)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "strategies" / "examples").mkdir(parents=True)
    (tmp_path / "strategies" / "examples" / "demo.py").write_text('''"""Demo strategy.

Second paragraph is not shown.
"""
from backtester import Strategy


class Demo(Strategy):
    universe = ["SPY", "QQQ"]
    interval = "1d"
    params = {"n": 20}
    param_grid = {"n": [10, 20]}

    def on_bar(self, ctx):
        pass


class Opts(Strategy):
    universe = ["SPY"]
    options_on = ["SPY"]

    def on_bar(self, ctx):
        pass
''')
    (tmp_path / "strategies" / "broken.py").write_text("def (:\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "backtester"\n')
    return tmp_path


@pytest.fixture
def client(project, monkeypatch):
    monkeypatch.setattr(service, "fetch_yahoo", lambda s, i, start, allow_nonpositive=False:
                        (_ for _ in ()).throw(DataError("Yahoo Finance has no data for that symbol (HTTP 404).")) if s == "BAD" else fake_bars())
    return TestClient(create_app(project))


def wait(client, task_id, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        t = client.get(f"/api/tasks/{task_id}").json()
        if t["status"] != "running":
            return t
        time.sleep(0.05)
    raise AssertionError("task did not finish")


# --- tasks ------------------------------------------------------------------------------------

def test_tasks_report_success_expected_failures_and_bugs():
    tasks = Tasks()
    ok = tasks.submit("ok", lambda log: (log("step one"), {"n": 1})[1])
    bad = tasks.submit("bad", lambda log: (_ for _ in ()).throw(DataError("Yahoo is limiting requests.")))
    bug = tasks.submit("bug", lambda log: 1 / 0)
    for _ in range(100):
        if all(tasks.get(i)["status"] != "running" for i in (ok, bad, bug)):
            break
        time.sleep(0.05)
    assert tasks.get(ok)["status"] == "done" and tasks.get(ok)["log"] == ["step one"] and tasks.get(ok)["result"] == {"n": 1}
    f = tasks.get(bad)
    assert f["status"] == "failed" and f["error"] == "Yahoo is limiting requests." and f["log"] == []     # the error is shown separately
    b = tasks.get(bug)
    assert b["status"] == "failed" and "ZeroDivisionError" in b["error"] and "Traceback" in "\n".join(b["log"])
    assert tasks.get("nope") is None and len(tasks.recent()) == 3
    assert tasks.clear_finished() == 3 and tasks.recent() == []


# --- strategies ---------------------------------------------------------------------------------

def test_strategy_discovery_reads_files_without_running_them(project):
    found = S.list_strategies(project)
    assert [s["name"] for s in found] == ["Demo", "Opts"]                      # the broken file is skipped
    demo = found[0]
    assert demo["path"] == "strategies/examples/demo.py" and demo["universe"] == ["SPY", "QQQ"]
    assert demo["description"] == "Demo strategy." and demo["params"] == {"n": 20} and demo["param_grid"] == {"n": [10, 20]}
    assert found[1]["options_on"] == ["SPY"] and found[1]["interval"] == "1d"


def test_data_needs_and_suggested_start(project, tmp_path):
    cache = Cache(project / "data" / "cache")
    demo, opts = S.list_strategies(project)
    cache.save("SPY", "1d", fake_bars(100, "2020-01-02 14:30"), source="yahoo")
    needs = S.data_needs(demo, cache)
    assert [(n["symbol"], n["cached"]) for n in needs] == [("SPY", True), ("QQQ", False), ("^IRX", False)]
    assert S.suggested_start(demo, needs) == "2020-02-01"                      # 30 days after the first bar
    onow = S.data_needs(opts, cache)
    assert [n["symbol"] for n in onow] == ["SPY", "^VIX", "^IRX"] and not onow[1]["cached"]
    assert S.suggested_start(demo, S.data_needs(demo, Cache(tmp_path / "empty"))) is None


# --- data endpoints -------------------------------------------------------------------------------

def test_data_page_flow_download_list_update_delete(client, project):
    r = client.post("/api/data/fetch", json={"symbols": "spy, qqq", "start": "2024-01-01", "interval": "1d"})
    t = wait(client, r.json()["task_id"])
    assert t["status"] == "done" and len(t["result"]["done"]) == 2 and any("Downloading SPY" in x for x in t["log"])
    rows = client.get("/api/data/list").json()["datasets"]
    assert [d["symbol"] for d in rows] == ["QQQ", "SPY"] and rows[0]["bars"] == 40 and "stale" in rows[0]
    upd = wait(client, client.post("/api/data/update").json()["task_id"])
    assert upd["status"] == "done" and len(upd["result"]["done"]) == 2
    rate = wait(client, client.post("/api/data/rates", json={}).json()["task_id"])
    assert rate["status"] == "done" and "Treasury bill yield" in rate["result"]["message"]
    assert client.post("/api/data/delete", json={"symbol": "SPY", "interval": "1d"}).json() == {"ok": True}
    assert [d["symbol"] for d in client.get("/api/data/list").json()["datasets"]] == ["QQQ", "^IRX"]
    assert client.post("/api/data/delete", json={"symbol": "SPY", "interval": "1d"}).status_code == 400


def test_failed_downloads_are_reported_not_hidden(client):
    t = wait(client, client.post("/api/data/fetch", json={"symbols": "BAD"}).json()["task_id"])
    assert t["status"] == "failed" and "no data for that symbol" in t["error"] and sum("FAILED" in x for x in t["log"]) == 1
    mixed = wait(client, client.post("/api/data/fetch", json={"symbols": "SPY BAD"}).json()["task_id"])
    assert mixed["status"] == "done" and mixed["result"]["failed"][0][0] == "BAD" and len(mixed["result"]["done"]) == 1


def test_fetch_missing_items_for_a_strategy(client, project):
    items = [{"symbol": "SPY", "interval": "1d"}, {"symbol": "^VIX", "interval": "1d"}]
    t = wait(client, client.post("/api/data/fetch", json={"items": items, "start": "2000-01-01"}).json()["task_id"])
    assert t["status"] == "done"
    needs = client.get("/api/strategies/needs?path=strategies/examples/demo.py").json()
    assert [(n["symbol"], n["cached"]) for n in needs["needs"]] == [("SPY", True), ("QQQ", False), ("^IRX", False)]
    assert [m["symbol"] for m in needs["missing"]] == ["QQQ", "^IRX"] and needs["suggested_start"]
    assert client.get("/api/strategies/needs?path=strategies/nope.py").status_code == 404
    assert client.get("/api/strategies/needs?path=../../etc/passwd").status_code == 404
    assert len(client.get("/api/strategies").json()["strategies"]) == 2


def test_data_endpoints_reject_bad_input(client):
    for body in ({"symbols": ""}, {"symbols": "SPY; rm -rf /"}, {"symbols": "SPY", "interval": "7m"},
                 {"symbols": "SPY", "start": "last year"}, {"items": [{"symbol": "../x", "interval": "1d"}]}):
        r = client.post("/api/data/fetch", json=body)
        assert r.status_code == 400 and r.json()["error"], body
    assert client.post("/api/data/fetch", content=b"not json").status_code == 400
    assert client.post("/api/data/rates", json={"start": "soon"}).status_code == 400
    assert client.post("/api/data/fetch", json={"symbols": "SPY"}, headers={"origin": "http://evil.example"}).status_code == 403
    assert client.get("/api/tasks/nope").status_code == 404


def test_dropped_price_files_are_imported(client):
    csv = fake_bars().reset_index().rename(columns={"index": "time"}).drop(columns="adj_factor").to_csv(index=False)
    files = [("files", ("QQQ.csv", csv.encode(), "text/csv")), ("files", ("notes.docx", b"x", "application/octet-stream"))]
    t = wait(client, client.post("/api/data/upload", files=files).json()["task_id"])
    assert t["status"] == "done" and [d["symbol"] for d in t["result"]["done"]] == ["QQQ"]
    assert t["result"]["failed"][0][0] == "notes.docx" and "only .csv and .json" in t["result"]["failed"][0][1]
    assert client.post("/api/data/upload", data={}).status_code == 400
    only_bad = wait(client, client.post("/api/data/upload", files=[("files", ("x.xlsx", b"x", "a/b"))]).json()["task_id"])
    assert only_bad["status"] == "failed"
    named = wait(client, client.post("/api/data/upload", data={"symbol": "iwm"}, files=[("files", ("prices.csv", csv.encode(), "text/csv"))]).json()["task_id"])
    assert named["result"]["done"][0]["symbol"] == "IWM"


def test_check_my_setup_runs_diagnostics(client, monkeypatch):
    monkeypatch.setattr("backtester.web.routes.diagnostics.run_checks", lambda cache: [
        {"name": "Python version", "ok": True, "detail": "3.13", "hint": ""},
        {"name": "Reach Yahoo", "ok": False, "detail": "no route", "hint": "Check the internet."}])
    t = wait(client, client.post("/api/data/check").json()["task_id"])
    assert t["status"] == "failed" and any("FAIL Reach Yahoo" in x and "Check the internet." in x for x in t["log"])
    assert "Some checks failed" in t["error"]
    monkeypatch.setattr("backtester.web.routes.diagnostics.run_checks", lambda cache: [{"name": "a", "ok": True, "detail": "x", "hint": ""}])
    assert wait(client, client.post("/api/data/check").json()["task_id"])["status"] == "done"


def test_refresh_clears_finished_task_messages(client):
    wait(client, client.post("/api/data/fetch", json={"symbols": "SPY"}).json()["task_id"])
    assert client.get("/api/tasks").json()["tasks"]
    assert client.post("/api/refresh").json()["cleared"] >= 1 and client.get("/api/tasks").json()["tasks"] == []


# --- papers ---------------------------------------------------------------------------------------

def test_read_pdf_finds_title_year_abstract(monkeypatch):
    info = read_pdf(PAPER, "x.pdf")
    assert info["title"].startswith("Momentum Strategies") and info["year"] == 2019 and info["pages"] == 1
    assert info["abstract"].startswith("We study a simple momentum rule") and "Keywords" not in info["abstract"]
    assert "Text of the paper" in info["text"] and info["warning"] is None
    with pytest.raises(PaperError, match="not a PDF"):
        read_pdf(b"hello", "x.pdf")
    with pytest.raises(PaperError, match="could not be read"):
        read_pdf(b"%PDF-1.4\ngarbage", "bad.pdf")
    with pytest.raises(PaperError, match="larger than"):
        read_pdf(b"%PDF-" + b"0" * (61 * 1024 * 1024), "big.pdf")
    tiny = read_pdf(pdf_bytes(["Short"]), "s.pdf")
    assert "Very little text" in tiny["warning"]


def test_paper_drop_edit_and_delete(client, project):
    r = client.post("/api/papers/upload", files=[("files", ("momentum.pdf", PAPER, "application/pdf")),
                                                 ("files", ("notes.txt", b"hi", "text/plain")),
                                                 ("files", ("broken.pdf", b"%PDF-1.4 nope", "application/pdf"))])
    res = r.json()["results"]
    assert res[0]["ok"] and res[0]["title"].startswith("Momentum") and res[0]["has_abstract"]
    assert not res[1]["ok"] and "not a PDF" in res[1]["error"] and not res[2]["ok"]
    pid = res[0]["id"]
    lib = Library(project / "research" / "library")
    p = lib.get(pid)
    assert p["pdf"] == f"files/{pid}.pdf" and p["claims_from_full_text"] and (project / "research" / "library" / "files" / f"{pid}.txt").exists()
    assert "momentum rule" in (project / "research" / "library" / p["text_file"]).read_text()
    pdf = client.get(f"/research/file/{pid}.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content == PAPER
    assert client.get("/research/file/..%2F..%2Fpyproject.toml").status_code == 404 and client.get("/research/file/nope.pdf").status_code == 404
    page = client.get("/research/library").text
    assert "Momentum Strategies" in page and "full text saved" in page and "Copy instructions for Claude" in page
    ok = client.post(f"/api/papers/{pid}/update", json={"title": "Momentum, revised", "year": "2020", "claims": "returns persist for a year\n\n fade after\n",
                                                        "status": "replicating", "claims_from_full_text": True})
    assert ok.json() == {"ok": True}
    p = lib.get(pid)
    assert p["title"] == "Momentum, revised" and p["year"] == 2020 and p["claims"] == ["returns persist for a year", "fade after"] and p["status"] == "replicating"
    assert client.post(f"/api/papers/{pid}/update", json={"status": "great"}).status_code == 400
    assert client.post(f"/api/papers/{pid}/update", json={"title": " "}).status_code == 400
    assert client.post("/api/papers/missing-paper/update", json={"title": "x"}).status_code == 404
    assert client.post("/api/papers/BAD%20ID/delete").status_code == 404
    assert client.post(f"/api/papers/{pid}/delete").json() == {"ok": True}
    assert lib.list() == [] and not (project / "research" / "library" / "files" / f"{pid}.pdf").exists()
    assert client.post(f"/api/papers/{pid}/delete").status_code == 404
    assert client.post("/api/papers/upload", data={}).status_code == 400


def test_paper_search_results_and_errors(client, monkeypatch):
    payload = {"results": [{"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/x", "title": "Tactical Asset Allocation",
                            "publication_year": 2007, "cited_by_count": 163,
                            "authorships": [{"author": {"display_name": f"Author {i}"}} for i in range(8)],
                            "primary_location": {"source": {"display_name": "Journal of Wealth Management"}},
                            "open_access": {"oa_url": "https://example.org/p.pdf"},
                            "abstract_inverted_index": {"A": [0], "timing": [2], "simple": [1], "model": [3]}},
                           {"id": "https://openalex.org/W2", "title": "", "authorships": []}]}
    rows = search_mod.parse_results(payload)
    assert len(rows) == 1 and rows[0]["abstract"] == "A simple timing model" and rows[0]["authors"].endswith("et al.")
    assert rows[0]["openalex_id"] == "W1" and rows[0]["open_pdf"] == "https://example.org/p.pdf" and rows[0]["cited_by"] == 163

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, *a): return json.dumps(payload).encode()
    monkeypatch.setattr(search_mod.urllib.request, "urlopen", lambda *a, **k: Resp())
    assert client.get("/api/papers/search?q=tactical asset allocation").json()["results"][0]["title"] == "Tactical Asset Allocation"
    assert client.get("/api/papers/search?q=ab").status_code == 400 and client.get("/api/papers/search?q=" + "x" * 300).status_code == 400
    monkeypatch.setattr(search_mod.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.HTTPError("u", 429, "x", {}, None)))
    r = client.get("/api/papers/search?q=momentum")
    assert r.status_code == 400 and "busy" in r.json()["error"]
    monkeypatch.setattr(search_mod.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError(TimeoutError("timed out"))))
    assert "did not answer in time" in client.get("/api/papers/search?q=momentum").json()["error"]


def test_add_a_found_paper_to_the_library(client, project):
    r = client.post("/api/papers/add", json={"title": "Tactical Asset Allocation", "authors": "M. Faber", "year": 2007, "venue": "JWM",
                                             "url": "https://doi.org/10.1/x", "abstract": "A simple timing model", "finding": "A simple timing model",
                                             "openalex_id": "W1", "doi": "10.1/x"})
    pid = r.json()["id"]
    p = Library(project / "research" / "library").get(pid)
    assert p["title"] == "Tactical Asset Allocation" and p["abstract"] == "A simple timing model" and p["openalex_id"] == "W1" and not p["pdf"]
    assert "abstract only" in client.get("/research/library").text
    assert client.post("/api/papers/add", json={"authors": "x"}).status_code == 400


# --- pages ---------------------------------------------------------------------------------------------

def test_every_page_renders_with_its_key_controls(client, project):
    home = client.get("/").text
    for text in ("Get data", "Run a backtest", "Read the results", "Research papers", "What this can and cannot do", "Refresh"):
        assert text in home, text
    data = client.get("/data").text
    for text in ("Download prices", "Interest rates", "Drag and drop price files here", "Check my setup", "Update all datasets", 'id="datasets"'):
        assert text in data, text
    new = client.get("/new").text
    assert "Demo" in new and "Quick look" in new and "Full checks" in new and 'name="strategy"' in new
    assert "Drag and drop PDF files here" in client.get("/research").text and "Search published papers" in client.get("/research").text
    assert "No results yet" in client.get("/runs").text
    assert client.get("/new?strategy=strategies/examples/demo.py").text.count("checked") >= 1
    err = client.post("/rerun", data={"strategy": "../x.py"})
    assert err.status_code == 400 and "Could not start the run" in err.text and "must be a .py file under strategies/" in err.text
    assert all("Refresh" in client.get(u).text for u in ("/", "/data", "/new", "/research", "/runs", "/compare"))


# --- launchers ---------------------------------------------------------------------------------------------

def test_launchers_exist_are_executable_and_the_venv_is_not_committed():
    assert os.access(ROOT / "start.sh", os.X_OK) and os.access(ROOT / "Start Backtester.command", os.X_OK)
    assert subprocess.run(["bash", "-n", str(ROOT / "start.sh")]).returncode == 0
    assert subprocess.run(["bash", "-n", str(ROOT / "Start Backtester.command")]).returncode == 0
    bat = (ROOT / "start.bat").read_text()
    assert "bt serve --open" in bat and "3.11" in bat and "pip install" in bat
    sh = (ROOT / "start.sh").read_text()
    assert "bt serve $OPEN" in sh and "3, 11" in sh and "install.log" in sh
    ignore = (ROOT / ".gitignore").read_text().split()
    assert ".venv/" in ignore
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", ".venv"], capture_output=True, text=True).stdout
    assert tracked.strip() == ""


# --- settings, search keys, rate limits -------------------------------------------------------------

def test_settings_file_is_private_and_never_echoed(project, monkeypatch, tmp_path):
    from backtester import paths, settings
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    assert not settings.is_set("openalex_api_key")
    settings.set_value("openalex_api_key", "  secret-key-123 ")
    assert settings.get("openalex_api_key") == "secret-key-123" and settings.is_set("openalex_api_key")
    f = tmp_path / "settings.local.json"
    assert f.exists() and (f.stat().st_mode & 0o077) == 0                     # not readable by others
    monkeypatch.setenv("OPENALEX_API_KEY", "from-env")
    assert settings.get("openalex_api_key") == "secret-key-123"               # the saved value wins
    settings.set_value("openalex_api_key", "")
    assert settings.get("openalex_api_key") == "from-env"
    with pytest.raises(KeyError):
        settings.set_value("something_else", "x")
    assert "settings.local.json" in (ROOT / ".gitignore").read_text().split()


def test_settings_endpoint_saves_without_revealing(client, monkeypatch, tmp_path):
    from backtester import paths
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    assert client.get("/api/settings").json() == {"openalex_key_set": False}
    r = client.post("/api/settings", json={"openalex_api_key": "abc123"})
    assert r.json() == {"openalex_key_set": True} and "abc123" not in r.text and "abc123" not in client.get("/api/settings").text
    assert client.post("/api/settings", json={"openalex_api_key": "has space"}).status_code == 400
    assert client.post("/api/settings", json={"openalex_api_key": ""}).json() == {"openalex_key_set": False}
    assert client.post("/api/settings", json={"openalex_api_key": "x"}, headers={"origin": "http://evil.example"}).status_code == 403
    assert "Search settings" in client.get("/research").text


def test_search_sends_the_key_as_a_header_and_explains_a_used_up_allowance(monkeypatch, tmp_path):
    from backtester import paths, settings
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    seen = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, *a): return b'{"results": []}'

    def fake(req, **k):
        seen["headers"] = dict(req.header_items()); seen["url"] = req.full_url
        return Resp()
    monkeypatch.setattr(search_mod.urllib.request, "urlopen", fake)
    search_mod.search_papers("momentum strategies")
    assert "Authorization" not in seen["headers"] and "api_key" not in seen["url"]
    settings.set_value("openalex_api_key", "k-42")
    search_mod.search_papers("momentum strategies")
    assert seen["headers"]["Authorization"] == "Bearer k-42" and "k-42" not in seen["url"]       # never in the address

    import io
    def limited(req, **k):
        raise urllib.error.HTTPError("u", 429, "x", {}, io.BytesIO(b'{"message": "This request has no API key, so it counts against the free daily budget"}'))
    settings.set_value("openalex_api_key", "")
    monkeypatch.setattr(search_mod.urllib.request, "urlopen", limited)
    with pytest.raises(search_mod.SearchError, match="allowance for your network is used up"):
        search_mod.search_papers("momentum strategies")
    settings.set_value("openalex_api_key", "k-42")
    with pytest.raises(search_mod.SearchError, match="Your paper-search key has used up"):
        search_mod.search_papers("momentum strategies")
    monkeypatch.setattr(search_mod.urllib.request, "urlopen", lambda req, **k: (_ for _ in ()).throw(urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b"{}"))))
    with pytest.raises(search_mod.SearchError, match="did not accept the saved key"):
        search_mod.search_papers("momentum strategies")


def test_doctor_does_not_call_a_rate_limit_ok(monkeypatch):
    import io

    from backtester import diagnostics
    monkeypatch.setattr(diagnostics.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.HTTPError("u", 429, "x", {}, io.BytesIO(b"{}"))))
    c = diagnostics._reach("https://example.org", "OpenAlex")
    assert not c["ok"] and "429" in c["detail"] and "free key" in c["hint"]
    monkeypatch.setattr(diagnostics.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(urllib.error.HTTPError("u", 404, "x", {}, io.BytesIO(b"{}"))))
    assert not diagnostics._reach("https://example.org", "Yahoo")["ok"]


def test_a_failed_task_does_not_repeat_its_error_three_times():
    tasks = Tasks()
    tid = tasks.submit("t", lambda log: (log("X: FAILED. no data"), (_ for _ in ()).throw(DataError("X: no data")))[1])
    for _ in range(100):
        if tasks.get(tid)["status"] != "running":
            break
        time.sleep(0.05)
    t = tasks.get(tid)
    assert t["status"] == "failed" and t["error"] == "X: no data"
    assert sum("no data" in line for line in t["log"]) == 1
