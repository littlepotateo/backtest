"""The dashboard application. Run it with `bt serve` (binds to this computer only)."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from types import SimpleNamespace

import plotly
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backtester import diagnostics, paths
from backtester.analysis.findings import ALL_TESTS, CHEAP_TESTS
from backtester.research import Library
from backtester.research.library import STATUSES, LibraryError
from backtester.research.requests import Requests, instruction
from backtester.version import server_version
from backtester.data import service
from backtester.data.cache import Cache
from backtester.web import data as D
from backtester.web import routes, surfaces
from backtester.web import strategies as S
from backtester.web.glossary import GLOSSARY
from backtester.web.jobs import BadRequest, Jobs
from backtester.web.tasks import Tasks

HERE = Path(__file__).parent
PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"


class NoCacheStatic(StaticFiles):
    """Static files that the browser must re-check every time, so an updated page never runs an old script."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def pct(x, digits: int = 1):
    return "n/a" if x is None else f"{x * 100:,.{digits}f}%"


def num(x, digits: int = 2):
    return "n/a" if x is None else f"{x:,.{digits}f}"


def create_app(root: str | Path | None = None) -> FastAPI:
    root = Path(root or paths.ROOT).resolve()
    runs_dir, cache_dir, lib_dir = root / "runs", root / "data" / "cache", root / "research" / "library"
    app = FastAPI(title="Strategy backtester", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.filters.update(pct=pct, num=num)
    templates.env.globals["glossary"] = GLOSSARY

    def static(name: str) -> str:
        """URL of a static file with its modification time, so a changed file is never served from an old cache."""
        try:
            return f"/static/{name}?v={int((HERE / 'static' / name).stat().st_mtime)}"
        except OSError:
            return f"/static/{name}"
    templates.env.globals["static"] = static
    templates.env.globals["server_version"] = server_version()
    templates.env.globals["missing_packages"] = diagnostics.missing_packages()
    jobs = Jobs(root, runs_dir, cache_dir)
    tasks = Tasks()
    env = SimpleNamespace(root=root, cache_dir=cache_dir, runs_dir=runs_dir, lib_dir=lib_dir, tasks=tasks)
    cache = Cache(cache_dir)

    @app.middleware("http")
    async def same_origin_posts(request: Request, call_next):
        """Refuse form posts that another website's page sent to this local server."""
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
                return JSONResponse({"error": "This request came from a different website or address than the dashboard, so it was refused. Open the dashboard at the address "
                                              "shown when it started and use that page.", "code": "BT-HTTP-403"}, status_code=403)
        return await call_next(request)

    @app.get("/static/plotly.min.js", include_in_schema=False)
    def plotly_js():
        return FileResponse(PLOTLY_JS, media_type="application/javascript")

    app.mount("/static", NoCacheStatic(directory=str(HERE / "static")), name="static")

    def page(request: Request, name: str, **ctx):
        return templates.TemplateResponse(request, name, {"nav": request.url.path, **ctx})

    def get_run(run_id: str) -> dict:
        try:
            return D.load_run(runs_dir, run_id, cache_dir)
        except D.NotFound:
            raise HTTPException(404, "no such run")

    # --- pages ------------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        datasets = service.dataset_table(cache)
        listing = D.list_runs(runs_dir)
        try:
            papers = Library(lib_dir).list()
        except LibraryError:               # the Research page explains a damaged library; the home page still opens
            papers = []
        return page(request, "home.html", datasets=datasets, has_rates=cache.has("^IRX", "1d"),
                    stale=[d for d in datasets if d["stale"]], runs=listing[:5], n_runs=len(listing),
                    papers=papers, strategies=S.list_strategies(root))

    @app.get("/runs", response_class=HTMLResponse)
    def runs(request: Request):
        return page(request, "runs.html", runs=D.list_runs(runs_dir))

    @app.get("/data", response_class=HTMLResponse)
    def data_page(request: Request):
        return page(request, "data.html", datasets=service.dataset_table(cache), has_rates=cache.has("^IRX", "1d"))

    @app.get("/new", response_class=HTMLResponse)
    def new_backtest(request: Request, strategy: str = ""):
        return page(request, "new.html", strategies=S.list_strategies(root), selected=strategy,
                    all_tests=ALL_TESTS, default_tests=CHEAP_TESTS)

    @app.get("/run/{run_id}", response_class=HTMLResponse)
    def run(request: Request, run_id: str):
        r = get_run(run_id)
        v = r["validation"] or {}
        charts = {
            "equity": D.series_json(r["equity"]), "benchmark": D.series_json(r["bench"]),
            "drawdown": D.series_json(r["drawdown"], 100), "bench_drawdown": D.series_json(r["bench_drawdown"], 100),
            "benchmark_name": r["meta"].get("benchmark"), "strategy_name": r["meta"].get("strategy"),
            "walkforward": [{"window": w["oos_start"], "is": w["is_sharpe"], "oos": w["oos_sharpe"]}
                            for w in v.get("walkforward", {}).get("windows", [])],
            "fan": v.get("montecarlo", {}).get("bootstrap", {}).get("fan"),
            "fan_days": v.get("metrics", {}).get("trading_days"),
            "kelly": v.get("kelly", {}).get("curve"), "kelly_at": v.get("kelly", {}).get("growth_at"),
            "kelly_point": v.get("kelly", {}).get("point_estimate"),
            "costs": v.get("costs"), "pricing": v.get("option_pricing"),
        }
        option_dates = D.option_dates(r["fills"]) if r["meta"].get("options") else []
        trades = r["trades"].tail(100).iloc[::-1]
        return page(request, "run.html", r=r, v=v, charts=charts, option_dates=option_dates,
                    trades=trades.to_dict(orient="records"), tests=v.get("tests_run", []))

    @app.get("/api/run/{run_id}/surface")
    def surface(run_id: str, kind: str, date: str, what: str = "gamma", right: str = "C"):
        r = get_run(run_id)
        if not r["meta"].get("options"):
            raise HTTPException(400, "this run has no option positions")
        try:
            on = dt.date.fromisoformat(date)
            if kind == "contract":
                if what not in ("gamma", "delta", "vega", "theta") or right not in ("C", "P"):
                    raise ValueError("bad greek or right")
                return surfaces.contract_surface(r["meta"], cache_dir, on, what, right)
            if kind == "position":
                if what not in ("gamma", "delta", "vega", "theta", "value"):
                    raise ValueError("bad quantity")
                return surfaces.position_surface(r["meta"], r["fills"], cache_dir, on, what)
            raise ValueError("kind must be contract or position")
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(400, str(e))

    @app.get("/compare", response_class=HTMLResponse)
    def compare(request: Request, a: str = "", b: str = ""):
        listing = D.list_runs(runs_dir)
        ra = get_run(a) if a else None
        rb = get_run(b) if b else None
        charts = None
        if ra and rb:
            charts = {"a": {"name": f"{ra['meta']['strategy']} ({a[:15]})", "short": ra["meta"]["strategy"],
                            **D.series_json(ra["equity"] / ra["initial"])},
                      "b": {"name": f"{rb['meta']['strategy']} ({b[:15]})", "short": rb["meta"]["strategy"],
                            **D.series_json(rb["equity"] / rb["initial"])}}
        return page(request, "compare.html", listing=listing, a=a, b=b, ra=ra, rb=rb, charts=charts)

    def library_context() -> dict:
        lib = Library(lib_dir)
        papers = []
        for p in lib.list():
            notes = lib_dir / f"{p['id']}.md"
            papers.append({**p, "comparison_html": D.render_markdown(lib.compare(p["id"])),
                           "notes_html": D.render_markdown(notes.read_text(encoding="utf-8")) if notes.exists() else "",
                           "run_ids": [Path(x["run"]).name for x in p["runs"]]})
        return {"papers": papers, "statuses": STATUSES}

    def requests_context() -> dict:
        titles = {p["id"]: p["title"] for p in Library(lib_dir).list()}
        reqs = [{**r, "instruction": instruction(r),
                 "found": [{"id": pid, "title": titles[pid]} for pid in r["papers"] if pid in titles]}
                for r in Requests(lib_dir).list()]
        return {"requests": reqs}

    @app.get("/research", response_class=HTMLResponse)
    def research(request: Request):
        return page(request, "research.html", **library_context(), **requests_context())

    @app.get("/research/requests", response_class=HTMLResponse)
    def research_requests(request: Request):
        return templates.TemplateResponse(request, "_requests.html", requests_context())

    @app.get("/research/library", response_class=HTMLResponse)
    def research_library(request: Request):
        return templates.TemplateResponse(request, "_library.html", library_context())

    @app.get("/research/file/{name}")
    def research_file(name: str):
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,120}\.pdf$", name):
            raise HTTPException(404, "no such file")
        f = (lib_dir / "files" / name).resolve()
        if f.parent != (lib_dir / "files").resolve() or not f.is_file():
            raise HTTPException(404, "no such file")
        return FileResponse(f, media_type="application/pdf", headers={"X-Content-Type-Options": "nosniff"})

    # --- re-runs ----------------------------------------------------------------------
    @app.get("/rerun/{run_id}", response_class=HTMLResponse)
    def rerun_form(request: Request, run_id: str):
        r = get_run(run_id)
        cfg, meta = r["meta"].get("config", {}), r["meta"]
        form = {"strategy": meta.get("strategy_file", ""), "start": cfg.get("start") or r["metrics"]["start"][:10],
                "end": cfg.get("end") or "", "cash": int(cfg.get("initial_cash", 100000)),
                "cost_multiplier": cfg.get("costs", {}).get("multiplier", 1.0), "paths": 2000, "risk_free": 0.02,
                "benchmark": meta.get("benchmark") or "",
                "params": "\n".join(f"{k}={json.dumps(v)}" for k, v in (meta.get("params") or {}).items())}
        return page(request, "rerun.html", r=r, form=form, all_tests=ALL_TESTS, default_tests=CHEAP_TESTS, error=None)

    @app.post("/rerun")
    async def rerun(request: Request):
        raw = await request.form()
        form = {k: raw.get(k) for k in raw.keys()}
        form["tests"] = raw.getlist("tests")
        try:
            return RedirectResponse(f"/jobs/{jobs.start(form)}", status_code=303)
        except BadRequest as e:
            return templates.TemplateResponse(request, "error.html", {"nav": "/new", "title": "Could not start the run", "message": str(e)}, status_code=400)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(request: Request, job_id: str):
        try:
            return page(request, "job.html", job=jobs.status(job_id))
        except BadRequest:
            raise HTTPException(404, "no such job")

    routes.register(app, env)
    return app
