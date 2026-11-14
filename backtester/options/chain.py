"""Option contracts and the synthetic (modelled) chain for one underlying.

`OptionModel` answers: which expiries and strikes exist on a date, which contract best
matches a target (days to expiry plus delta, strike or percent of spot), and what a
contract is worth. A real historical chain would replace this class behind the same
methods. See docs/research/options-pricing.md.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backtester.options import pricing as bs
from backtester.options.surface import VolSurface

MULTIPLIER = 100
OPEN_FRACTION = 0.27        # share of a calendar day left at the opening bell (6.5 of 24 hours)


@dataclass(frozen=True, order=True)
class OptionContract:
    underlying: str
    expiry: dt.date
    strike: float
    right: str               # "C" or "P"

    def __str__(self) -> str:
        return f"{self.underlying} {self.expiry.isoformat()} {self.right} {self.strike:g}"

    def intrinsic(self, spot: float) -> float:
        return max(spot - self.strike, 0.0) if self.right == "C" else max(self.strike - spot, 0.0)


def third_friday(year: int, month: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(4 - first.weekday()) % 7 + 14)


def _day(now) -> dt.date:
    t = pd.Timestamp(now)
    if t.tzinfo is not None:
        t = t.tz_convert("America/New_York")
    return t.date()


class OptionModel:
    def __init__(self, symbol: str, surface: VolSurface, rates: pd.Series | None = None,
                 dividend_yield=0.0, strike_step: float | None = None,
                 weeklies: bool = False):
        self.symbol, self.surface, self.rates = symbol, surface, rates
        self.dividend_yield, self.strike_step, self.weeklies = dividend_yield, strike_step, weeklies

    # --- inputs ---------------------------------------------------------------------
    def rate(self, now) -> float:
        if self.rates is None or len(self.rates) == 0:
            return 0.0
        i = self.rates.index.searchsorted(pd.Timestamp(_day(now)), side="right") - 1
        return float(self.rates.iloc[i]) if i >= 0 else 0.0

    def q(self, now, at_open: bool = False) -> float:
        """Dividend yield known at `now`: a number, or a series looked up by date."""
        dy = self.dividend_yield
        if not isinstance(dy, pd.Series):
            return float(dy)
        day = pd.Timestamp(_day(now) - dt.timedelta(days=1) if at_open else _day(now))
        i = dy.index.searchsorted(day, side="right") - 1
        return float(dy.iloc[i]) if i >= 0 else 0.0

    def years_left(self, contract: OptionContract, now, at_open: bool = False) -> float:
        days = (contract.expiry - _day(now)).days
        if days < 0:
            return 0.0
        return (days + (OPEN_FRACTION if at_open else 0.0)) / 365

    # --- the chain --------------------------------------------------------------------
    def expiries(self, now, months: int = 14) -> list[dt.date]:
        today = _day(now)
        out = []
        y, m = today.year, today.month
        for _ in range(months):
            out.append(third_friday(y, m))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        if self.weeklies:
            d = today + dt.timedelta(days=(4 - today.weekday()) % 7)
            out += [d + dt.timedelta(weeks=i) for i in range(8)]
        return sorted({e for e in out if e >= today})

    def step(self, spot: float) -> float:
        if self.strike_step:
            return self.strike_step
        return 0.5 if spot < 25 else 1.0 if spot < 1000 else 5.0

    def strikes(self, spot: float, width: float = 0.5) -> np.ndarray:
        step = self.step(spot)
        lo, hi = math.floor(spot * (1 - width) / step), math.ceil(spot * (1 + width) / step)
        return np.arange(max(lo, 1), hi + 1) * step

    # --- valuation --------------------------------------------------------------------
    def _inputs(self, contract, spot, now, at_open):
        t = self.years_left(contract, now, at_open)
        r, q = self.rate(now), self.q(now, at_open)
        forward = spot * math.exp((r - q) * t)
        asof = _day(now) - dt.timedelta(days=1) if at_open else now   # today's level is unknown at the open
        vol = self.surface.vol(asof, t, contract.strike, forward) if t > 0 else 0.2
        return t, r, q, vol

    def value(self, contract: OptionContract, spot: float, now, at_open: bool = False) -> float:
        """Modelled mid price per share."""
        t, r, q, vol = self._inputs(contract, spot, now, at_open)
        return float(bs.price(spot, contract.strike, t, r, q, vol, contract.right))

    def greeks(self, contract: OptionContract, spot: float, now, at_open: bool = False) -> dict:
        t, r, q, vol = self._inputs(contract, spot, now, at_open)
        return {**bs.greeks(spot, contract.strike, t, r, q, vol, contract.right), "vol": vol}

    def half_spread(self, value: float) -> float:
        return float(self.surface.half_spread(value))

    # --- selection ---------------------------------------------------------------------
    def select(self, now, spot: float, right: str, dte: int, *, delta: float | None = None,
               strike: float | None = None, pct: float | None = None, min_dte: int = 1) -> OptionContract:
        """The listed contract closest to the request. Give exactly one of `delta`
        (absolute value, e.g. 0.30), `strike`, or `pct` (strike as a fraction of spot,
        e.g. 1.05)."""
        if sum(x is not None for x in (delta, strike, pct)) != 1:
            raise ValueError("give exactly one of delta, strike or pct")
        today = _day(now)
        choices = [e for e in self.expiries(now) if (e - today).days >= min_dte]
        expiry = min(choices, key=lambda e: abs((e - today).days - dte))
        grid = self.strikes(spot)
        if delta is not None:
            t = (expiry - today).days / 365
            r, q = self.rate(now), self.q(now)
            forward = spot * math.exp((r - q) * t)
            vols = self.surface.vol(now, t, grid, forward)
            deltas = np.abs(bs.greeks(spot, grid, t, r, q, vols, right)["delta"])
            k = grid[int(np.argmin(np.abs(deltas - abs(delta))))]
        else:
            target = strike if strike is not None else spot * pct
            k = grid[int(np.argmin(np.abs(grid - target)))]
        return OptionContract(self.symbol, expiry, float(k), right)
