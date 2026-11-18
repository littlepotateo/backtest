"""Position sizing of the intraday momentum study: mean-variance weight, utility and certainty-equivalent gain (equations 6-8)."""

from __future__ import annotations

import pandas as pd

TRADING_DAYS = 252


def mean_variance_weight(rhat: pd.Series, sigma2: pd.Series, gamma: float = 5.0, lo: float = -0.5, hi: float = 1.5) -> pd.Series:
    """Equation (6): w = (1 / gamma) * rhat / sigma2, limited to [lo, hi] (the paper allows borrowing or shorting 50%)."""
    return (rhat / (gamma * sigma2)).clip(lower=lo, upper=hi)


def portfolio_returns(w: pd.Series, r13: pd.Series, rf: pd.Series | float = 0.0) -> pd.Series:
    """Weight w in the market for the last half-hour, the rest in the risk-free asset (zero by default: a half-hour of T-bill interest)."""
    return w * r13 + (1 - w) * rf


def utility(returns: pd.Series, gamma: float = 5.0, periods: int = TRADING_DAYS) -> float:
    """Equation (7): U = mean - gamma/2 * variance, annualised (mean x 252, variance x 252)."""
    r = pd.Series(returns).dropna()
    return float(r.mean() * periods - gamma / 2 * r.var(ddof=1) * periods)


def certainty_equivalent(forecast_returns: pd.Series, benchmark_returns: pd.Series, gamma: float = 5.0) -> float:
    """Equation (8): CER = U2 - U1, the gain of using the regression forecast over the historical-average forecast."""
    return utility(forecast_returns, gamma) - utility(benchmark_returns, gamma)
