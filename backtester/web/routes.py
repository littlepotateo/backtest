"""Dashboard routes for data, strategies, papers and housekeeping (JSON for the page scripts)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from backtester import diagnostics, settings
from backtester.data import service
from backtester.data.cache import INTERVAL_SECONDS, Cache
from backtester.data.yahoo import _INTERVALS, DataError
from backtester.research import Library
from backtester.errors import CodedError
from backtester.research.ingest import PaperError, read_pdf
from backtester.research.requests import Requests
from backtester.version import server_version
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exception_handlers import http_exception_handler as default_http_handler
from backtester.research.search import SearchError, search_papers
from backtester.web import data as D
from backtester.web import strategies as S

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PAPER_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,120}$")


def error_page(request: Request, e: Exception, code: str, status: int = 500) -> HTMLResponse:
    """A readable page for a failure while building a page, in place of the bare 'Internal Server Error'.
    It stands alone (no template) so it still works when the shared page layout is what failed."""
    import html
    import traceback
    frames = "\n".join(f"{Path(f.filename).name}:{f.lineno} in {f.name}: {(f.line or '').strip()}"
                       for f in traceback.extract_tb(e.__traceback__)[-6:])
    expected = isinstance(e, CodedError)
    what = html.escape(str(e)) if expected else f"{html.escape(type(e).__name__)}: {html.escape(str(e))}"
    body = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Problem [{code}]</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:820px;margin:40px auto;padding:0 16px;color:#1a1a19}}
code,pre{{background:#f0efec;border-radius:6px;padding:2px 6px}}pre{{padding:12px;overflow:auto;font-size:13px}}</style></head><body>
<h1>The dashboard could not build this page</h1>
<p><strong>{what}</strong></p><p>Error code: <code>{code}</code> &nbsp; Page: <code>{html.escape(request.url.path)}</code>
&nbsp; Server version: <code>{html.escape(server_version())}</code></p>
{'' if expected else '<p>This is a bug or an unreadable file in your project folders. Send me the code and the lines below.</p>'}
{'' if expected else f'<details open><summary>Where it happened</summary><pre>{html.escape(frames)}</pre></details>'}
<p>If it says a package is missing, or the server may be old: close the dashboard and start it again with <code>start.sh</code>
(Mac: <code>Start Backtester.command</code>, Windows: <code>start.bat</code>). The terminal window running the dashboard has the full details.
Codes are explained in <code>docs/error-codes.md</code>.</p><p><a href="/data">Data page</a> · <a href="/">Home</a></p></body></html>"""
    return HTMLResponse(body, status_code=status)


def fail(message: str, status: int = 400, code: str | None = None) -> JSONResponse:
    """An error answer: a plain message plus a short code the user can quote (see docs/error-codes.md)."""
    return JSONResponse({"error": message, "code": code or f"BT-HTTP-{status}"}, status_code=status)


async def body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise DataError("The request was not understood.", "BT-HTTP-400")
    if not isinstance(data, dict):
        raise DataError("The request was not understood.", "BT-HTTP-400")
    return data


def check_interval(interval: str) -> str:
    if interval not in _INTERVALS or interval not in INTERVAL_SECONDS:
        raise DataError(f"Bar size must be one of: {', '.join(_INTERVALS)}.", "BT-DATA-003")
    return interval


def check_date(value, name: str = "start") -> str | None:
    value = (value or "").strip() if isinstance(value, str) else value
    if not value:
        return None
    if not DATE.match(value):
        raise DataError(f"The {name} date must look like 2005-01-31.", "BT-DATA-010")
    return value


def register(app: FastAPI, ctx) -> None:
    cache = Cache(ctx.cache_dir)
    tasks, runs_dir = ctx.tasks, ctx.runs_dir

    @app.exception_handler(Exception)
    async def unexpected(request: Request, e: Exception):
        import traceback
        traceback.print_exception(e)
        if isinstance(e, UnicodeError):
            code = "BT-FILE-001"
            message = ("A file could not be read or written because of a text-encoding problem (a character the computer's default "
                       "encoding does not have). Restart with start.bat / start.sh, which switch to UTF-8, and try again.")
            return fail(message, 500, code) if request.url.path.startswith("/api/") else error_page(request, e, code)
        if not request.url.path.startswith("/api/"):
            return error_page(request, e, "BT-HTTP-500")
        return fail(f"Something went wrong inside the dashboard ({type(e).__name__}). The terminal window running it has the details; "
                    f"if a package is missing, restart with start.sh.", 500)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, e: StarletteHTTPException):
        """Plain 'Not Found' / 'Method Not Allowed' answers become explanations with a code."""
        if not request.url.path.startswith("/api/"):
            return await default_http_handler(request, e)
        if e.status_code == 404 and e.detail in ("Not Found", None, ""):
            return JSONResponse({"error": f"This dashboard server has no “{request.method} {request.url.path}” feature. The server is most likely "
                                           f"running an older version of the program than this page. Close it and start it again with start.sh "
                                           f"(Mac: Start Backtester.command, Windows: start.bat). Server version: {server_version()}.",
                                 "code": "BT-HTTP-404", "version": server_version()}, status_code=404)
        if e.status_code == 405:
            return fail(f"“{request.url.path}” does not accept {request.method} requests (the page and the server may be different versions).", 405)
        return fail(str(e.detail), e.status_code)

    @app.exception_handler(CodedError)
    async def coded_error(request: Request, e: CodedError):
        if not request.url.path.startswith("/api/") and request.method == "GET":
            return error_page(request, e, e.code, 500)
        return fail(str(e), 400, e.code)

    # --- tasks ---------------------------------------------------------------------------
    @app.get("/api/tasks/{task_id}")
    def task(task_id: str):
        t = tasks.get(task_id)
        return t if t else fail("No such task.", 404)

    @app.get("/api/tasks")
    def recent_tasks():
        return {"tasks": tasks.recent()}

    @app.post("/api/refresh")
    def refresh():
        return {"cleared": tasks.clear_finished()}

    # --- data ------------------------------------------------------------------------------
    @app.get("/api/data/list")
    def data_list():
        return {"datasets": service.dataset_table(cache)}

    @app.post("/api/data/fetch")
    async def data_fetch(request: Request):
        b = await body(request)
        start = check_date(b.get("start"))
        if b.get("items") is not None:
            items = []
            for it in b["items"][:40]:
                sym = service.clean_symbols(str(it.get("symbol", "")))[0]
                items.append((sym, check_interval(it.get("interval", "1d")), check_date(it.get("start")) or start))
        else:
            interval = check_interval(b.get("interval", "1d"))
            items = [(s, interval, start) for s in service.clean_symbols(str(b.get("symbols", "")))]

        def run(log):
            done, failed = [], []
            for sym, interval, st in items:
                try:
                    done.append(service.fetch_symbol(cache, sym, interval, st, log))
                except DataError as e:
                    log(f"{sym}: FAILED. {e}")
                    failed.append([sym, str(e)])
            if failed and not done:
                raise DataError("; ".join(f"{s}: {m}" for s, m in failed), "BT-DATA-011")
            log(f"Finished: {len(done)} downloaded" + (f", {len(failed)} failed." if failed else "."))
            return {"done": done, "failed": failed}
        title = "Download " + ", ".join(s for s, _, _ in items[:6]) + ("…" if len(items) > 6 else "")
        return {"task_id": tasks.submit(title, run)}

    @app.post("/api/data/rates")
    async def data_rates(request: Request):
        b = await body(request)
        start = check_date(b.get("start")) or "1990-01-01"
        return {"task_id": tasks.submit("Download interest rates", lambda log: service.fetch_rates(cache, start, log))}

    @app.post("/api/data/update")
    def data_update():
        return {"task_id": tasks.submit("Update all datasets", lambda log: service.update_all(cache, log))}

    @app.post("/api/data/upload")
    async def data_upload(request: Request):
        form = await request.form()
        files = [(f.filename, await f.read()) for f in form.getlist("files") if getattr(f, "filename", "")]
        if not files:
            raise DataError("Drop at least one .csv or .json price file.", "BT-DATA-007")
        if sum(len(c) for _, c in files) > 200 * 1024 * 1024:
            raise DataError("Those files are too large (limit 200 MB in total).", "BT-DATA-012")
        symbol = (form.get("symbol") or "").strip() or None
        interval = (form.get("interval") or "").strip() or None
        if symbol:
            symbol = service.clean_symbols(symbol)[0]
        if interval:
            check_interval(interval)

        def run(log):
            done, failed = [], []
            for name, content in files:
                try:
                    done.append(service.import_file(cache, name, content, symbol if len(files) == 1 else None, interval, log))
                except DataError as e:
                    log(f"{name}: FAILED. {e}")
                    failed.append([name, str(e)])
            if failed and not done:
                raise DataError("; ".join(f"{n}: {m}" for n, m in failed), "BT-DATA-011")
            return {"done": done, "failed": failed}
        return {"task_id": tasks.submit(f"Import {len(files)} file(s)", run)}

    @app.post("/api/data/delete")
    async def data_delete(request: Request):
        b = await body(request)
        service.delete_dataset(cache, service.clean_symbols(str(b.get("symbol", "")))[0], check_interval(b.get("interval", "1d")))
        return {"ok": True}

    @app.post("/api/data/check")
    def data_check():
        def run(log):
            results = diagnostics.run_checks(cache)
            for c in results:
                log(f"{'ok  ' if c['ok'] else 'FAIL'} {c['name']}: {c['detail']}" + (f"  → {c['hint']}" if not c["ok"] and c["hint"] else ""))
            if not all(c["ok"] for c in results):
                raise DataError("Some checks failed. See the lines above.", "BT-DATA-013")
            return {"checks": results}
        return {"task_id": tasks.submit("Check my setup", run)}

    # --- strategies --------------------------------------------------------------------------
    @app.get("/api/strategies")
    def strategies():
        return {"strategies": S.list_strategies(ctx.root)}

    @app.get("/api/strategies/needs")
    def strategy_needs(path: str):
        found = [s for s in S.list_strategies(ctx.root) if s["path"] == path]
        if not found:
            return fail("No such strategy.", 404)
        needs = S.data_needs(found[0], cache)
        return {"strategy": found[0], "needs": needs, "suggested_start": S.suggested_start(found[0], needs),
                "missing": [n for n in needs if not n["cached"]]}

    # --- runs ---------------------------------------------------------------------------------
    @app.post("/api/runs/{run_id}/delete")
    def delete_run(run_id: str):
        try:
            d = D.safe_run_dir(runs_dir, run_id)
        except D.NotFound:
            return fail("No such run.", 404)
        shutil.rmtree(d)
        return {"ok": True}

    # --- settings ---------------------------------------------------------------------------------
    @app.get("/api/settings")
    def get_settings():
        return {"openalex_key_set": settings.is_set("openalex_api_key")}      # never the key itself

    @app.post("/api/settings")
    async def save_settings(request: Request):
        b = await body(request)
        key = str(b.get("openalex_api_key", "")).strip()
        if len(key) > 200 or any(c.isspace() for c in key):
            raise DataError("That does not look like a key.", "BT-SET-001")
        settings.set_value("openalex_api_key", key)
        return {"openalex_key_set": settings.is_set("openalex_api_key")}

    # --- papers ---------------------------------------------------------------------------------
    @app.get("/api/papers/search")
    def paper_search(q: str):
        return {"results": search_papers(q)}

    @app.post("/api/papers/add")
    async def paper_add(request: Request):
        b = await body(request)
        title = str(b.get("title", "")).strip()
        if not title:
            raise DataError("A paper needs a title.")
        lib = Library(ctx.lib_dir)
        year = int(b["year"]) if str(b.get("year") or "").isdigit() else None
        pid = lib.add(title, authors=str(b.get("authors", ""))[:500], year=year, venue=str(b.get("venue", ""))[:200],
                      url=str(b.get("url", ""))[:500], finding=str(b.get("finding", ""))[:3000], doi=str(b.get("doi", ""))[:200],
                      abstract=str(b.get("abstract", ""))[:3000], openalex_id=str(b.get("openalex_id", ""))[:40])
        return {"id": pid}

    @app.post("/api/requests")
    async def request_create(request: Request):
        b = await body(request)
        return Requests(ctx.lib_dir).create(str(b.get("query", "")), str(b.get("notes", "")))

    @app.post("/api/requests/{rid}/delete")
    def request_delete(rid: str):
        try:
            Requests(ctx.lib_dir).delete(rid)
        except KeyError:
            return fail("No such request.", 404)
        return {"ok": True}

    @app.post("/api/papers/upload")
    async def paper_upload(request: Request):
        form = await request.form()
        lib = Library(ctx.lib_dir)
        out = []
        for f in form.getlist("files"):
            name = getattr(f, "filename", "")
            if not name:
                continue
            try:
                if not name.lower().endswith(".pdf"):
                    raise PaperError(f"{name} is not a PDF. Drop PDF files here.", "BT-PDF-006")
                data = await f.read()
                info = read_pdf(data, name)
                pid = lib.add(info["title"], authors=info["authors"], year=info["year"], doi=info["doi"],
                              abstract=info["abstract"], finding=info["abstract"][:600])
                lib.attach_pdf(pid, data, info["text"])
                out.append({"file": name, "ok": True, "id": pid, "title": info["title"], "pages": info["pages"],
                            "year": info["year"], "has_abstract": bool(info["abstract"]), "warning": info["warning"]})
            except PaperError as e:
                out.append({"file": name, "ok": False, "error": str(e), "code": e.code})
        if not out:
            raise PaperError("Drop at least one PDF file.", "BT-PDF-007")
        return {"results": out}

    @app.post("/api/papers/{pid}/update")
    async def paper_update(pid: str, request: Request):
        if not PAPER_ID.match(pid):
            return fail("No such paper.", 404)
        b = await body(request)
        lib = Library(ctx.lib_dir)
        try:
            lib.get(pid)
            fields = {k: b[k] for k in ("title", "authors", "year", "venue", "url", "finding", "status", "claims_from_full_text") if k in b}
            if "claims" in b:
                fields["claims"] = [c for c in (b["claims"].splitlines() if isinstance(b["claims"], str) else b["claims"])]
            if "title" in fields and not str(fields["title"]).strip():
                raise DataError("A paper needs a title.")
            lib.update(pid, **fields)
        except KeyError:
            return fail("No such paper.", 404)
        except ValueError as e:
            raise DataError(str(e))
        return {"ok": True}

    @app.post("/api/papers/{pid}/delete")
    def paper_delete(pid: str):
        if not PAPER_ID.match(pid):
            return fail("No such paper.", 404)
        try:
            Library(ctx.lib_dir).delete(pid)
        except KeyError:
            return fail("No such paper.", 404)
        return {"ok": True}
