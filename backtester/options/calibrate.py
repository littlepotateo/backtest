"""Fit the volatility-surface parameters to a snapshot of real option quotes and report
how far the model's prices are from the market's.

Snapshot file (JSON):
  {"symbol": "SPY", "date": "2026-11-13", "spot": 754.37, "source": "...",
   "quotes": [{"expiry": "2026-12-18", "strike": 680, "right": "P", "bid": 2.46, "ask": 2.50}, ...]}
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import asdict
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from backtester import paths
from backtester.options import pricing as bs
from backtester.options.surface import SurfaceParams, VolSurface


def calibrate(snapshot: dict, level: float, rate: float, dividend_yield: float) -> dict:
    """`level` is the un-scaled volatility level on the snapshot date (e.g. VIX / 100)."""
    import pandas as pd
    day = dt.date.fromisoformat(snapshot["date"])
    spot = float(snapshot["spot"])
    rows = []
    for q in snapshot["quotes"]:
        mid = (q["bid"] + q["ask"]) / 2
        t = (dt.date.fromisoformat(q["expiry"]) - day).days / 365
        iv = bs.implied_vol(mid, spot, q["strike"], t, rate, dividend_yield, q["right"])
        if t > 0 and math.isfinite(iv):
            rows.append({**q, "mid": mid, "t": t, "iv": iv,
                         "forward": spot * math.exp((rate - dividend_yield) * t)})
    if len(rows) < 4:
        raise ValueError("need at least four usable quotes to calibrate")
    t = np.array([r["t"] for r in rows])
    k = np.array([float(r["strike"]) for r in rows])
    fwd = np.array([r["forward"] for r in rows])
    iv = np.array([r["iv"] for r in rows])
    series = pd.Series([level], index=pd.to_datetime([snapshot["date"]]))

    def model_iv(x):
        p = SurfaceParams(ratio=x[0], skew=x[1], curvature=x[2], term=x[3])
        surf = VolSurface(p, series, "calibration")
        return np.array([surf.vol(snapshot["date"], ti, ki, fi) for ti, ki, fi in zip(t, k, fwd)])

    fit = least_squares(lambda x: model_iv(x) - iv, x0=[0.9, -0.13, 0.03, 0.04],
                        bounds=([0.3, -0.6, 0.0, -0.3], [2.0, 0.2, 0.3, 0.3]))
    half = np.array([(r["ask"] - r["bid"]) / 2 for r in rows])
    mids = np.array([r["mid"] for r in rows])
    params = SurfaceParams(ratio=float(fit.x[0]), skew=float(fit.x[1]), curvature=float(fit.x[2]),
                           term=float(fit.x[3]), half_spread=float(np.median(half / mids)),
                           min_half_spread=0.01, calibrated=True)
    fitted = model_iv(fit.x)
    table = []
    for r, miv in zip(rows, fitted):
        price = float(bs.price(spot, r["strike"], r["t"], rate, dividend_yield, miv, r["right"]))
        table.append({"expiry": r["expiry"], "strike": r["strike"], "right": r["right"],
                      "market_mid": r["mid"], "model_price": price,
                      "price_error_pct": (price / r["mid"] - 1) * 100,
                      "market_iv": r["iv"], "model_iv": float(miv)})
    errs = np.array([abs(x["price_error_pct"]) for x in table])
    return {"symbol": snapshot["symbol"], "date": snapshot["date"], "spot": spot,
            "quote_source": snapshot.get("source", "unknown"), "level": level, "rate": rate,
            "dividend_yield": dividend_yield, "quotes_used": len(rows), "params": asdict(params),
            "mean_abs_price_error_pct": float(errs.mean()), "max_abs_price_error_pct": float(errs.max()),
            "iv_rmse": float(np.sqrt(np.mean((fitted - iv) ** 2))), "table": table,
            "caveat": "Fitted to one day's quotes; the same shape is applied to all of history."}


def save_params(symbol: str, report: dict, path: str | Path | None = None) -> None:
    """Write or replace the [SYMBOL] section of the surface config."""
    path = Path(path or paths.SURFACE)
    text = path.read_text() if path.exists() else (
        "# Volatility-surface parameters per underlying, fitted by `bt calibrate-options`.\n")
    lines, skip = [], False
    for line in text.splitlines():
        if line.strip().startswith("["):
            skip = line.strip() == f"[{symbol.upper()}]"
        if not skip:
            lines.append(line)
    p = report["params"]
    block = [f"[{symbol.upper()}]",
             f"# fitted {report['date']} to {report['quotes_used']} quotes ({report['quote_source']}); "
             f"mean price error {report['mean_abs_price_error_pct']:.1f}%"]
    block += [f"{k} = {str(v).lower() if isinstance(v, bool) else repr(round(v, 6))}" for k, v in p.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n\n" + "\n".join(block) + "\n")
