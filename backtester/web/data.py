"""Reading saved runs for the dashboard. Nothing here changes a run."""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path

import markdown
import numpy as np
import pandas as pd

from backtester.analysis.metrics import daily_equity
from backtester.explain import explain, trust_level
from backtester.explain.report import RISK_TESTS

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
NY = "America/New_York"
OPTION_SYMBOL = re.compile(r"^(?P<u>\S+) (?P<e>\d{4}-\d{2}-\d{2}) (?P<r>[CP]) (?P<k>[\d.]+)$")


class NotFound(Exception):
    pass


def safe_run_dir(runs_dir: Path, run_id: str) -> Path:
    """The folder of a run, refusing anything that is not a plain folder name inside runs/."""
    if not SAFE_ID.match(run_id or ""):
        raise NotFound(run_id)
    d = (runs_dir / run_id).resolve()
    if d.parent != runs_dir.resolve() or not (d / "meta.json").exists():
        raise NotFound(run_id)
    return d


def render_markdown(text: str) -> str:
    """Markdown to HTML with any raw HTML in the source escaped."""
    return markdown.markdown(html.escape(text, quote=False), extensions=["tables"])


def _read_json(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def summarise(d: Path) -> dict | None:
    meta, metrics = _read_json(d / "meta.json"), _read_json(d / "metrics.json")
    if meta is None or metrics is None:
        return None
    validation = _read_json(d / "validation.json")
    flags = validation["flags"] if validation else None
    trust = trust_level(flags)[0] if flags is not None else None
    return {
        "id": d.name, "strategy": meta.get("strategy"), "universe": ", ".join(meta.get("universe", [])),
        "interval": meta.get("interval"), "params": meta.get("params", {}),
        "start": metrics["start"][:10], "end": metrics["end"][:10], "metrics": metrics,
        "backend": meta.get("backend"), "trust": trust,
        "high": sum(f["severity"] == "high" and f["test"] not in RISK_TESTS for f in flags) if flags else None,
        "medium": sum(f["severity"] == "medium" and f["test"] not in RISK_TESTS for f in flags) if flags else None,
        "risk_warning": any(f["test"] in RISK_TESTS and f["severity"] in ("high", "medium") for f in flags) if flags else None,
        "validated": validation is not None, "has_options": bool(meta.get("options")),
        "sources": sorted({v.get("source", "?") for v in meta.get("data", {}).values()}),
    }


def list_runs(runs_dir: Path) -> list[dict]:
    if not runs_dir.exists():
        return []
    out = [summarise(d) for d in sorted(runs_dir.iterdir(), reverse=True) if d.is_dir() and SAFE_ID.match(d.name)]
    return [r for r in out if r]


def daily(equity: pd.Series, tz: str = NY) -> pd.Series:
    return daily_equity(equity, tz)


def benchmark_equity(cache_root: Path, symbol: str | None, index: pd.DatetimeIndex, initial: float) -> pd.Series | None:
    """Buy-and-hold of `symbol` (dividends reinvested) on the run's own days, starting at `initial`."""
    from backtester.data.cache import Cache
    if not symbol:
        return None
    cache = Cache(cache_root)
    if not cache.has(symbol, "1d"):
        return None
    b = cache.load(symbol, "1d")
    px = b["close"] * b["adj_factor"]
    px.index = px.index.tz_convert(NY).normalize().tz_localize(None)
    px = px[~px.index.duplicated(keep="last")].reindex(index, method="ffill").dropna()
    return None if px.empty else px / px.iloc[0] * initial


def monthly_table(eq: pd.Series, initial: float) -> dict:
    """Month-by-month returns, years as rows. Values are fractions."""
    me = eq.groupby([eq.index.year, eq.index.month]).last()
    prev = me.shift(1)
    prev.iloc[0] = initial
    ret = (me / prev - 1)
    years = sorted({y for y, _ in ret.index})
    rows = []
    for y in years:
        months = [float(ret[(y, m)]) if (y, m) in ret.index else None for m in range(1, 13)]
        year_end = eq[eq.index.year == y].iloc[-1]
        start = eq[eq.index.year < y].iloc[-1] if (eq.index.year < y).any() else initial
        rows.append({"year": y, "months": months, "total": float(year_end / start - 1)})
    return {"rows": rows}


def load_run(runs_dir: Path, run_id: str, cache_root: Path) -> dict:
    d = safe_run_dir(runs_dir, run_id)
    meta = _read_json(d / "meta.json")
    metrics = _read_json(d / "metrics.json")
    eq_df = pd.read_parquet(d / "equity.parquet")
    initial = float(meta.get("config", {}).get("initial_cash", eq_df["equity"].iloc[0]))
    eq = daily(eq_df["equity"], meta.get("config", {}).get("timezone", NY))
    bench = benchmark_equity(cache_root, meta.get("benchmark"), eq.index, initial)
    dd = eq / eq.cummax() - 1
    bdd = bench / bench.cummax() - 1 if bench is not None else None
    validation = _read_json(d / "validation.json")
    flags = validation["flags"] if validation else []
    # Regenerated from the saved results, so it always matches the current wording and the page's other
    # numbers; a stored explanation.md may have been written by an older version of the explainer.
    if validation:
        explanation = explain(validation, meta)
    else:
        explanation = (d / "explanation.md").read_text() if (d / "explanation.md").exists() else None
    narrative = (d / "narrative.md").read_text() if (d / "narrative.md").exists() else None
    trades = pd.read_parquet(d / "trades.parquet")
    return {
        "id": run_id, "dir": d, "meta": meta, "metrics": metrics, "validation": validation, "flags": flags,
        "trust": trust_level(flags) if validation else None, "initial": initial,
        "evidence_flags": [f for f in flags if f["test"] not in RISK_TESTS],
        "risk_flags": [f for f in flags if f["test"] in RISK_TESTS and f["severity"] in ("high", "medium")],
        "explanation_html": render_markdown(explanation) if explanation else None,
        "narrative_html": render_markdown(narrative) if narrative else None,
        "equity": eq, "bench": bench, "drawdown": dd, "bench_drawdown": bdd,
        "monthly": monthly_table(eq, initial), "trades": trades,
        "fills": pd.read_parquet(d / "fills.parquet"),
    }


def series_json(s: pd.Series | None, scale: float = 1.0) -> dict | None:
    if s is None:
        return None
    return {"x": [t.strftime("%Y-%m-%d") for t in s.index], "y": [round(float(v) * scale, 6) for v in s.to_numpy()]}


def option_positions(fills: pd.DataFrame, on: dt.date) -> dict:
    """Option positions {contract: contracts} open at the close of `on`, rebuilt from fills."""
    from backtester.options.chain import OptionContract
    held: dict = {}
    if fills.empty:
        return held
    times = pd.DatetimeIndex(fills["time"]).tz_convert(NY)
    for (_, row), t in zip(fills.iterrows(), times):
        m = OPTION_SYMBOL.match(str(row["symbol"]))
        if not m or t.date() > on:
            continue
        c = OptionContract(m["u"], dt.date.fromisoformat(m["e"]), float(m["k"]), m["r"])
        held[c] = held.get(c, 0.0) + float(row["qty"]) / 100
    return {c: q for c, q in held.items() if abs(q) > 1e-9 and c.expiry > on}


def option_dates(fills: pd.DataFrame, limit: int = 80) -> list[str]:
    """Fill dates on which an option position was open afterwards (newest first)."""
    if fills.empty:
        return []
    is_opt = fills["symbol"].astype(str).map(lambda x: bool(OPTION_SYMBOL.match(x)))
    days = sorted({t.date() for t in pd.DatetimeIndex(fills.loc[is_opt, "time"]).tz_convert(NY)})
    out = [d for d in days if option_positions(fills, d)]
    return [d.isoformat() for d in reversed(out)][:limit]
