"""3D greeks surfaces for a saved options run, as JSON for the dashboard."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from backtester.data.cache import Cache
from backtester.engine.backend import build_option_models, load_rates
from backtester.options import greeks_surface as gs
from backtester.options.surface import SurfaceParams
from backtester.web.data import NY, option_positions


def _model(meta: dict, cache_root: Path, upto: dt.date):
    cache = Cache(cache_root)
    sym = next(iter(meta["options"]["underlyings"]))
    bars = cache.load(sym, "1d")
    bars = bars[bars.index.tz_convert(NY).date <= upto]
    if bars.empty:
        raise ValueError(f"no {sym} prices on or before {upto}")
    used = meta["options"]["underlyings"][sym]
    params = SurfaceParams(**{k: used[k] for k in SurfaceParams.__dataclass_fields__ if k in used})
    model = build_option_models([sym], {sym: bars}, load_rates(cache), cache, params={sym: params})[sym]
    return sym, model, float(bars["close"].iloc[-1]), bars.index[-1]


def contract_surface(meta: dict, cache_root: Path, on: dt.date, greek: str, right: str) -> dict:
    sym, model, spot, now = _model(meta, cache_root, on)
    s = gs.contract_surface(model, now, spot, greek, right, dollar=(greek == "gamma"))
    return _pack(s, f"{sym} {'call' if right == 'C' else 'put'} {s['z_label']} on {now.date()} (modelled)", "sequential")


def position_surface(meta: dict, fills: pd.DataFrame, cache_root: Path, on: dt.date, what: str) -> dict:
    sym, model, spot, now = _model(meta, cache_root, on)
    positions = option_positions(fills, on)
    if not positions:
        raise ValueError(f"no option position was open on {on}")
    shares = 0.0
    s = gs.position_surface(model, positions, now, spot, what, shares=shares)
    legs = [f"{'+' if q > 0 else ''}{q:g} {c.right} {c.strike:g} {c.expiry:%b %d}" for c, q in sorted(positions.items())]
    out = _pack(s, f"Open option position on {now.date()}: {what}", "diverging" if what != "value" else "sequential")
    out["legs"] = legs
    out["note"] = "Option legs only; shares held alongside are not included."
    return out


def _pack(s: dict, title: str, scale: str) -> dict:
    return {"x": np.round(s["x"], 4).tolist(), "y": np.round(s["y"], 4).tolist(),
            "z": np.round(s["z"], 6).tolist(), "x_label": s["x_label"], "y_label": s["y_label"],
            "z_label": s["z_label"], "title": title, "scale": scale, "spot": s["spot"]}
