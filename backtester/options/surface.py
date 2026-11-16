"""A parametric implied-volatility surface for pricing options through history.

    vol(date, T, K) = level(date) * term(T) * (1 + skew * m + curvature * m^2)
    m = ln(K / forward) / (atm * sqrt(T))          (how many standard deviations away)

`level` comes from a volatility index (VIX for SPY, VXN for QQQ, RVX for IWM) times a
ratio, or from realised volatility times a ratio when no index exists. The smile moves
with the underlying ("sticky moneyness"), which is an assumption.
See docs/research/options-pricing.md.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

VOL_MIN, VOL_MAX = 0.05, 3.0
VOL_INDEX = {"SPY": "^VIX", "QQQ": "^VXN", "IWM": "^RVX"}


@dataclass(frozen=True)
class SurfaceParams:
    ratio: float = 0.90        # at-the-money 30-day volatility as a fraction of the index level
    skew: float = -0.13        # relative change in volatility per standard deviation of moneyness
    curvature: float = 0.03
    term: float = 0.04         # volatility scales with (T / 30 days) ** term
    half_spread: float = 0.02  # half the bid/ask spread as a fraction of the option's value
    min_half_spread: float = 0.01   # ... but at least this many dollars per share
    call_wing: float = 1.5     # skew stops lowering volatility beyond this many standard
                               # deviations above the money (real call wings flatten)
    calibrated: bool = False   # True once fitted to a live chain

    @classmethod
    def load(cls, symbol: str, path: str | Path = "config/vol_surface.toml") -> "SurfaceParams":
        path = Path(path)
        if path.exists():
            raw = tomllib.loads(path.read_text()).get(symbol.upper())
            if raw:
                return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})
        return cls()

    def scaled(self, level: float = 1.0, skew: float = 1.0) -> "SurfaceParams":
        """A copy with the volatility level and skew multiplied (pricing-sensitivity test)."""
        return SurfaceParams(**{**asdict(self), "ratio": self.ratio * level, "skew": self.skew * skew})


def realised_vol(close: pd.Series, window: int = 21) -> pd.Series:
    """Annualised trailing volatility of daily log returns, known at each day's close."""
    return np.log(close).diff().rolling(window).std() * np.sqrt(252)


class VolSurface:
    def __init__(self, params: SurfaceParams, level: pd.Series, source: str):
        """`level` is the un-scaled volatility level by date (index value / 100, or
        realised volatility); `source` describes where it came from."""
        self.params, self.source = params, source
        level = level.dropna()
        idx = pd.DatetimeIndex(level.index)
        if idx.tz is not None:
            idx = idx.tz_convert("America/New_York").normalize().tz_localize(None)
        self.level = pd.Series(level.to_numpy(dtype=float), index=idx)
        self.level = self.level[~self.level.index.duplicated(keep="last")].sort_index()

    def level_on(self, date) -> float:
        """Latest level known on or before `date` (never a later one)."""
        d = pd.Timestamp(date)
        if d.tzinfo is not None:
            d = d.tz_convert("America/New_York").normalize().tz_localize(None)
        i = self.level.index.searchsorted(d.normalize(), side="right") - 1
        if i < 0:
            raise ValueError(
                f"no volatility level available on or before {d.date()}: the volatility index or the "
                f"realised-volatility history starts later. Start the backtest later (about a month after the first "
                f"price) or cache a longer history.")
        return float(self.level.iloc[i])

    def atm(self, date, t):
        t = np.maximum(np.asarray(t, dtype=float), 1 / 365)
        return self.level_on(date) * self.params.ratio * (t / (30 / 365)) ** self.params.term

    def vol(self, date, t, strike, forward):
        """Implied volatility for expiry `t` years away at `strike`."""
        t = np.maximum(np.asarray(t, dtype=float), 1 / 365)
        atm = self.atm(date, t)
        m = np.log(np.asarray(strike, dtype=float) / forward) / (atm * np.sqrt(t))
        m = np.clip(m, -4.0, self.params.call_wing)
        shape = np.maximum(1 + self.params.skew * m + self.params.curvature * m ** 2, 0.3)
        out = np.clip(atm * shape, VOL_MIN, VOL_MAX)
        return float(out) if out.ndim == 0 else out

    def half_spread(self, value):
        """Dollars per share paid to cross half the bid/ask spread."""
        return np.maximum(np.asarray(value, dtype=float) * self.params.half_spread,
                          self.params.min_half_spread)
