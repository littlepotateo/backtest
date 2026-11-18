"""Timing signals and performance statistics of the intraday momentum study (Gao, Han, Li and Zhou, 2017, section 4.1)."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def timing_signal(r1: pd.Series, r12: pd.Series | None = None) -> pd.Series:
    """Equation (4), or (5) when `r12` is given. Position in the last half-hour: +1 long, -1 short, 0 flat.
    One signal: long if r1 > 0, short otherwise. Two signals: long only if both are positive, short if both are <= 0, flat if they disagree."""
    up1 = r1 > 0
    if r12 is None:
        return pd.Series(np.where(up1, 1, -1), index=r1.index, dtype=int)
    up12 = r12 > 0
    return pd.Series(np.select([up1 & up12, ~up1 & ~up12], [1, -1], default=0), index=r1.index, dtype=int)


def strategy_returns(signal: pd.Series, r13: pd.Series) -> pd.Series:
    """The last-half-hour return earned by the position, closed at the close each day."""
    return signal * r13


def summarize(returns: pd.Series, periods: int = TRADING_DAYS) -> dict:
    """The statistics of the paper's Table 6: annualised by multiplying the daily mean by 252 (the strategy trades once a day even
    though it is exposed for half an hour), standard deviation scaled by the square root, Sharpe ratio without a risk-free rate,
    skewness, raw (not excess) kurtosis, and the success rate (days with a zero or positive return)."""
    r = pd.Series(returns).dropna()
    sd = r.std(ddof=1)
    return {"n": int(len(r)), "mean_pct": float(r.mean() * periods * 100), "sd_pct": float(sd * np.sqrt(periods) * 100),
            "sharpe": float(r.mean() / sd * np.sqrt(periods)) if sd > 0 else float("nan"),
            "skew": float(r.skew()), "kurtosis": float(r.kurt() + 3), "success_pct": float((r >= 0).mean() * 100)}
