"""The Research page must say what is wrong instead of failing silently: stale scripts, missing packages, server errors."""

import sys

import pytest
from fastapi.testclient import TestClient

from backtester import diagnostics
from backtester.research import search as search_mod
from backtester.research.ingest import PaperError, read_pdf
from backtester.web.app import create_app
from tests.test_web_stage8 import PAPER


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path), raise_server_exceptions=False)


def test_static_files_are_never_served_from_a_stale_browser_cache(client):
    r = client.get("/static/research.js")
    assert r.status_code == 200 and "no-cache" in r.headers["cache-control"]
    page = client.get("/research").text
    assert "/static/research.js?v=" in page and "/static/common.js?v=" in page and "/static/style.css?v=" in page


def test_a_missing_pdf_reader_is_named_not_called_a_bad_pdf(monkeypatch):
    monkeypatch.setitem(sys.modules, "pypdf", None)          # makes `import pypdf` fail
    with pytest.raises(PaperError) as e:
        read_pdf(PAPER, "x.pdf")
    assert "pypdf" in str(e.value) and "not installed" in str(e.value) and "could not be read" not in str(e.value)


def test_missing_packages_show_a_banner_on_every_page(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, "missing_packages", lambda: ["pypdf", "multipart"])
    c = TestClient(create_app(tmp_path))
    for path in ("/", "/research", "/data"):
        html = c.get(path).text
        assert "pypdf" in html and "multipart" in html and "start.sh" in html, path
    monkeypatch.setattr(diagnostics, "missing_packages", lambda: [])
    assert "packages are missing" not in TestClient(create_app(tmp_path)).get("/research").text


def test_unexpected_errors_in_api_calls_come_back_as_a_readable_message(client, monkeypatch):
    def boom(q):
        raise RuntimeError("kaboom")
    monkeypatch.setattr("backtester.web.routes.search_papers", boom)
    r = client.get("/api/papers/search?q=momentum")
    assert r.status_code == 500 and "RuntimeError" in r.json()["error"] and "terminal" in r.json()["error"]


def test_rate_limit_message_points_to_the_current_settings_name_and_the_other_source():
    import io
    import urllib.error
    e = urllib.error.HTTPError("u", 429, "x", {}, io.BytesIO(b'{"message": "This request has no API key ... budget"}'))
    msg = search_mod.rate_limit_message(e, False)
    assert "OpenAlex settings" in msg and "Consensus" in msg and "Search settings" not in msg
