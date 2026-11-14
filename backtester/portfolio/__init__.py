"""Portfolio weighting methods for investment strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtester.portfolio.bl import View, black_litterman  # noqa: F401
from backtester.portfolio.weights import (equal_weight, inverse_volatility, ledoit_wolf,  # noqa: F401
                                          mean_variance, min_variance, risk_contributions,
                                          risk_parity)

METHODS = ("equal", "inverse_vol", "risk_parity", "min_variance", "mean_variance", "black_litterman")
PERIODS_PER_YEAR = 252


def allocate(method: str, returns: pd.DataFrame, *, views: list[View] | None = None,
             prior_weights: dict | None = None, expected_returns: dict | None = None,
             risk_aversion: float = 2.5, tau: float = 0.05, max_weight: float | None = 0.4,
             long_only: bool = True, periods_per_year: int = PERIODS_PER_YEAR) -> dict:
    """Weights for the columns of `returns` (per-period returns up to the decision date).

    Returns {"weights": {symbol: weight}, "method": ..., "shrinkage": ..., and, for
    Black-Litterman, the prior and posterior returns}. Covariance is Ledoit-Wolf shrunk
    and annualised. If there is too little history (fewer than twice as many rows as
    assets) it falls back to inverse-volatility weights and says so."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; choose from {METHODS}")
    returns = returns.dropna()
    symbols = list(returns.columns)
    n = len(symbols)
    out: dict = {"method": method, "observations": int(len(returns)), "notes": []}
    if method == "equal" or n == 1:
        out["weights"] = dict(zip(symbols, equal_weight(n).tolist()))
        return out
    if len(returns) < 2 * n:
        var = returns.var(ddof=1).to_numpy() if len(returns) > 1 else np.ones(n)
        w = inverse_volatility(np.diag(np.where(var > 0, var, 1.0)))
        out.update(weights=dict(zip(symbols, w.tolist())), method="inverse_vol")
        out["notes"].append(f"Too little history for {method} ({len(returns)} rows for {n} assets): "
                            "used inverse-volatility weights.")
        return out
    cov, shrink = ledoit_wolf(returns.to_numpy())
    cov = cov * periods_per_year
    out["shrinkage"] = shrink
    if method == "inverse_vol":
        w = inverse_volatility(cov)
    elif method == "risk_parity":
        w = risk_parity(cov)
    elif method == "min_variance":
        w = min_variance(cov, long_only, max_weight)
    elif method == "mean_variance":
        if expected_returns is None:
            mu = returns.mean().to_numpy() * periods_per_year
            out["notes"].append("Expected returns are historical averages: very noisy inputs.")
        else:
            mu = np.array([expected_returns[s] for s in symbols], dtype=float)
        w = mean_variance(mu, cov, risk_aversion, long_only, max_weight)
    else:
        if prior_weights is None:
            ref = inverse_volatility(cov)
            equilibrium = False
        else:
            ref = np.array([prior_weights[s] for s in symbols], dtype=float)
            equilibrium = True
        res = black_litterman(symbols, cov, ref, views or [], risk_aversion=risk_aversion, tau=tau,
                              long_only=long_only, max_weight=max_weight, equilibrium_prior=equilibrium)
        out.update({k: v for k, v in res.as_dict().items() if k != "notes"})
        out["notes"] += res.notes
        out["views"] = [{"weights": v.weights, "value": v.value, "confidence": v.confidence}
                        for v in (views or [])]
        return out
    out["weights"] = dict(zip(symbols, np.asarray(w).tolist()))
    return out
