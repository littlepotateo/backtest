"""Greeks as surfaces, for 3D charts.

contract_surface: one option right's greek over strike x days to expiry on a given date.
position_surface: a whole position's greek (or value) over underlying price x days forward.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

from backtester.options import pricing as bs
from backtester.options.chain import MULTIPLIER, OptionContract, OptionModel, _day

GREEKS = ("delta", "gamma", "vega", "theta")


def contract_surface(model: OptionModel, now, spot: float, greek: str = "gamma", right: str = "C",
                     width: float = 0.2, max_days: int = 180, n: int = 60, dollar: bool = False) -> dict:
    """`dollar=True` with gamma gives the P&L curvature per 1% move per share
    (gamma * spot^2 / 100), which is comparable across underlyings."""
    if greek not in GREEKS:
        raise ValueError(f"greek must be one of {GREEKS}")
    strikes = np.linspace(spot * (1 - width), spot * (1 + width), n)
    days = np.linspace(1, max_days, n)
    r, q = model.rate(now), model.dividend_yield
    z = np.empty((len(days), len(strikes)))
    for i, d in enumerate(days):
        t = d / 365
        fwd = spot * np.exp((r - q) * t)
        vol = model.surface.vol(now, t, strikes, fwd)
        z[i] = bs.greeks(spot, strikes, t, r, q, vol, right)[greek]
    if dollar and greek == "gamma":
        z = z * spot ** 2 / 100
    return {"x": strikes, "y": days, "z": z, "x_label": "strike", "y_label": "days to expiry",
            "z_label": ("dollar " if dollar else "") + greek, "spot": spot}


def position_surface(model: OptionModel, positions: dict[OptionContract, float], now, spot: float,
                     what: str = "gamma", shares: float = 0.0, width: float = 0.2, n: int = 60) -> dict:
    """`positions` maps contract -> contracts (negative = short). `what` is a greek or
    "value". Legs drop out (to intrinsic value, zero greeks) once they expire."""
    if what not in GREEKS + ("value",):
        raise ValueError(f"what must be a greek or 'value'")
    today = _day(now)
    last = max((c.expiry - today).days for c in positions)
    prices = np.linspace(spot * (1 - width), spot * (1 + width), n)
    forward_days = np.linspace(0, max(last - 0.5, 0.5), n)
    r, q = model.rate(now), model.dividend_yield
    z = np.zeros((len(forward_days), len(prices)))
    for i, fd in enumerate(forward_days):
        for c, qty in positions.items():
            t = ((c.expiry - today).days - fd) / 365
            if t <= 0:
                if what == "value":
                    z[i] += qty * MULTIPLIER * bs.intrinsic(prices, c.strike, c.right)
                continue
            fwd = prices * np.exp((r - q) * t)
            vol = model.surface.vol(now, t, c.strike, fwd)
            if what == "value":
                z[i] += qty * MULTIPLIER * bs.price(prices, c.strike, t, r, q, vol, c.right)
            else:
                z[i] += qty * MULTIPLIER * bs.greeks(prices, c.strike, t, r, q, vol, c.right)[what]
        if what == "delta":
            z[i] += shares
        elif what == "value":
            z[i] += shares * prices
    return {"x": prices, "y": forward_days, "z": z, "x_label": "underlying price",
            "y_label": "days from now", "z_label": f"position {what}", "spot": spot}


def write_html(surface: dict, path, title: str) -> None:
    """A standalone rotatable 3D chart (Plotly loaded from its CDN when the file is opened)."""
    import json
    from pathlib import Path
    data = [{"type": "surface", "x": np.asarray(surface["x"]).tolist(), "y": np.asarray(surface["y"]).tolist(),
             "z": np.asarray(surface["z"]).tolist(), "colorscale": "Viridis",
             "colorbar": {"title": {"text": surface["z_label"]}}}]
    layout = {"title": {"text": title}, "margin": {"l": 0, "r": 0, "t": 50, "b": 0},
              "scene": {"xaxis": {"title": {"text": surface["x_label"]}},
                        "yaxis": {"title": {"text": surface["y_label"]}},
                        "zaxis": {"title": {"text": surface["z_label"]}}}}
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>%s</title>"
            "<script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script></head>"
            "<body style='margin:0'><div id='c' style='width:100vw;height:100vh'></div>"
            "<script>Plotly.newPlot('c', %s, %s, {responsive: true});</script></body></html>"
            % (title, json.dumps(data), json.dumps(layout)))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(html)
