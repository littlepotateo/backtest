"""Windows reads and writes text files in a legacy code page unless told otherwise. A paper containing a letter that code page
lacks (the 'fi' ligature U+FB01, arrows, Greek) made the upload fail with UnicodeEncodeError. Every text file is now UTF-8."""

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backtester.research import Library
from backtester.web import routes
from backtester.web.app import create_app

ROOT = Path(__file__).resolve().parent.parent
TRICKY = "Moving averages ﬁlter returns → α ≈ 5% — “quoted” éè 中文"


def test_no_text_file_is_opened_without_an_encoding():
    """A text-mode read/write without encoding= uses the platform default, which is not UTF-8 on Windows."""
    bad = []
    for p in (ROOT / "backtester").rglob("*.py"):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                continue
            name, kws = n.func.attr, {k.arg for k in n.keywords}
            if name in ("read_text", "write_text") and "encoding" not in kws and len(n.args) < (1 if name == "read_text" else 2):
                bad.append(f"{p.relative_to(ROOT)}:{n.lineno} {name}")
            elif name == "open" and not ast.unparse(n.func.value).startswith("webbrowser") and "encoding" not in kws:
                mode = n.args[0].value if n.args and isinstance(n.args[0], ast.Constant) else next(
                    (k.value.value for k in n.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)), "r")
                if "b" not in str(mode):
                    bad.append(f"{p.relative_to(ROOT)}:{n.lineno} open")
    assert not bad, bad


def test_library_round_trips_any_text(tmp_path):
    lib = Library(tmp_path / "library")
    pid = lib.add(TRICKY, authors=TRICKY, year=2020, finding=TRICKY, claims=[TRICKY])
    lib.attach_pdf(pid, b"%PDF-1.4", TRICKY * 3)
    assert lib.get(pid)["finding"] == TRICKY and lib.get(pid)["claims"] == [TRICKY]
    assert (tmp_path / "library" / "files" / f"{pid}.txt").read_bytes().decode("utf-8") == TRICKY * 3
    assert TRICKY in (tmp_path / "library" / f"{pid}.md").read_text(encoding="utf-8")


def test_uploading_a_paper_with_ligatures_and_symbols_works(tmp_path, monkeypatch):
    info = {"title": "Trend ﬁnding", "authors": "A. Éric", "year": 2020, "doi": "", "abstract": TRICKY, "pages": 1, "text": TRICKY * 50,
            "warning": None}
    monkeypatch.setattr(routes, "read_pdf", lambda data, name: info)
    c = TestClient(create_app(tmp_path), raise_server_exceptions=False)
    r = c.post("/api/papers/upload", files=[("files", ("p.pdf", b"%PDF-1.4 x", "application/pdf"))])
    assert r.status_code == 200 and r.json()["results"][0]["ok"], r.text
    page = c.get("/research/library")
    assert page.status_code == 200 and "Trend" in page.text
    pid = r.json()["results"][0]["id"]
    assert "→" in (tmp_path / "research" / "library" / "files" / f"{pid}.txt").read_text(encoding="utf-8")


def test_settings_and_requests_keep_unicode(tmp_path):
    from backtester.research.requests import Requests
    r = Requests(tmp_path).create("momentum — 中文 ﬁlter", "guidance → α")
    assert Requests(tmp_path).get(r["id"])["query"] == "momentum — 中文 ﬁlter"


def test_launchers_force_utf8_and_keep_packages_current():
    bat, sh = (ROOT / "start.bat").read_text(encoding="utf-8"), (ROOT / "start.sh").read_text(encoding="utf-8")
    assert "PYTHONUTF8=1" in bat and "PYTHONUTF8=1" in sh
    assert ".installed" not in bat and "pip install --quiet -e ." in bat          # reinstalls on every start so new dependencies arrive
    assert "fonttools" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_the_cli_survives_a_console_that_cannot_print_these_letters(tmp_path, capfd):
    from backtester import cli
    import sys
    sys.stdout.reconfigure(encoding="cp1252", errors="strict") if hasattr(sys.stdout, "reconfigure") else None
    try:
        cli.main(["--cache", str(tmp_path), "paper", "add", "--library", str(tmp_path / "lib"), "--title", TRICKY])
    except SystemExit:
        pass
    assert (tmp_path / "lib" / "index.json").exists()


def test_ids_keep_the_letters_of_ligatures_and_accents():
    from backtester.research.library import slug
    assert slug("Trend ﬁnding étude", 2020) == "trend-finding-etude-2020"


def test_an_encoding_failure_has_its_own_code(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise UnicodeEncodeError("charmap", "ﬁ", 0, 1, "character maps to <undefined>")
    monkeypatch.setattr(Library, "attach_pdf", boom)
    monkeypatch.setattr(routes, "read_pdf", lambda d, n: {"title": "T", "authors": "", "year": 2020, "doi": "", "abstract": "", "pages": 1, "text": "x", "warning": None})
    c = TestClient(create_app(tmp_path), raise_server_exceptions=False)
    r = c.post("/api/papers/upload", files=[("files", ("p.pdf", b"%PDF-1.4 x", "application/pdf"))])
    assert r.status_code == 500 and r.json()["code"] == "BT-FILE-001" and "UTF-8" in r.json()["error"]
