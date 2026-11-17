"""The dashboard application. Run it with `bt serve` (binds to this computer only)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import plotly
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backtester import paths
from backtester.analysis.findings import ALL_TESTS, CHEAP_TESTS
from backtester.research import Library
from backtester.web import data as D
from backtester.web import surfaces
from backtester.web.jobs import BadRequest, Jobs

HERE = Path(__file__).parent
PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"


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
    jobs = Jobs(root, runs_dir, cache_dir)

    @app.middleware("http")
    async def same_origin_posts(request: Request, call_next):
        """Refuse form posts that another website's page sent to this local server."""
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
                return JSONResponse({"error": "cross-site request refused"}, status_code=403)
        return await call_next(request)

    @app.get("/static/plotly.min.js", include_in_schema=False)
    def plotly_js():
        return FileResponse(PLOTLY_JS, media_type="application/javascript")

    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    def page(request: Request, name: str, **ctx):
        return templates.TemplateResponse(request, name, {"nav": request.url.path, **ctx})

    def get_run(run_id: str) -> dict:
        try:
            return D.load_run(runs_dir, run_id, cache_dir)
        except D.NotFound:
            raise HTTPException(404, "no such run")

    # --- pages ------------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def runs(request: Request):
        return page(request, "runs.html", runs=D.list_runs(runs_dir))

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

    @app.get("/research", response_class=HTMLResponse)
    def research(request: Request):
        lib = Library(lib_dir)
        papers = []
        for p in lib.list():
            notes = lib_dir / f"{p['id']}.md"
            papers.append({**p, "comparison_html": D.render_markdown(lib.compare(p["id"])),
                           "notes_html": D.render_markdown(notes.read_text()) if notes.exists() else "",
                           "run_ids": [Path(x["run"]).name for x in p["runs"]]})
        return page(request, "research.html", papers=papers)

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
            return HTMLResponse(f"<p>Could not start: {e}</p><p><a href='javascript:history.back()'>Back</a></p>", status_code=400)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(request: Request, job_id: str):
        try:
            return page(request, "job.html", job=jobs.status(job_id))
        except BadRequest:
            raise HTTPException(404, "no such job")

    return app
