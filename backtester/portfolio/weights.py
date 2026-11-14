"""Covariance estimation and the baseline weighting methods.
See docs/research/portfolio-allocation.md."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize


def ledoit_wolf(returns) -> tuple[np.ndarray, float]:
    """Shrunk covariance of a (T x N) return matrix and the shrinkage used (0-1).
    Ledoit & Wolf (2004): shrinks the sample covariance toward a scaled identity."""
    x = np.asarray(returns, dtype=float)
    x = x - x.mean(axis=0)
    n, p = x.shape
    sample = x.T @ x / n
    mu = np.trace(sample) / p
    delta = ((sample - mu * np.eye(p)) ** 2).sum() / p
    x2 = x ** 2
    beta = ((x2.T @ x2).sum() / n - (sample ** 2).sum()) / (n * p)
    beta = min(beta, delta)
    shrink = 0.0 if delta == 0 else beta / delta
    return (1 - shrink) * sample + shrink * mu * np.eye(p), float(shrink)


def _bounds(n: int, long_only: bool, max_weight: float | None):
    lo = 0.0 if long_only else -1.0
    hi = 1.0 if max_weight is None else max_weight
    if hi * n < 1 - 1e-12:
        raise ValueError(f"a cap of {hi:.0%} on {n} assets cannot add up to 100%")
    return [(lo, hi)] * n


def _solve(objective, n: int, long_only: bool, max_weight: float | None, start=None) -> np.ndarray:
    res = minimize(objective, np.full(n, 1 / n) if start is None else start, method="SLSQP",
                   bounds=_bounds(n, long_only, max_weight),
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"ftol": 1e-12, "maxiter": 500})
    if not res.success:
        raise RuntimeError(f"weight optimisation failed: {res.message}")
    w = np.where(np.abs(res.x) < 1e-10, 0.0, res.x)
    return w / w.sum()


def equal_weight(n: int) -> np.ndarray:
    return np.full(n, 1 / n)


def inverse_volatility(cov) -> np.ndarray:
    inv = 1 / np.sqrt(np.diag(np.asarray(cov, dtype=float)))
    return inv / inv.sum()


def risk_contributions(w, cov) -> np.ndarray:
    """Each asset's share of total portfolio variance (sums to 1)."""
    w, cov = np.asarray(w, dtype=float), np.asarray(cov, dtype=float)
    rc = w * (cov @ w)
    return rc / rc.sum()


def risk_parity(cov) -> np.ndarray:
    """Weights at which every asset contributes the same share of portfolio risk
    (Maillard, Roncalli & Teiletche 2010), long-only."""
    cov = np.asarray(cov, dtype=float)
    n = len(cov)
    scale = np.sqrt(np.diag(cov)).mean()
    c = cov / scale ** 2

    # convex form (Spinu 2013): minimise 0.5 y'Cy - (1/n) sum(log y), then normalise
    def f(y):
        return 0.5 * y @ c @ y - np.log(y).sum() / n

    def grad(y):
        return c @ y - 1 / (n * y)

    res = minimize(f, np.ones(n), jac=grad, method="L-BFGS-B", bounds=[(1e-8, None)] * n,
                   options={"ftol": 1e-15, "gtol": 1e-12, "maxiter": 2000})
    return res.x / res.x.sum()


def min_variance(cov, long_only: bool = True, max_weight: float | None = None) -> np.ndarray:
    cov = np.asarray(cov, dtype=float)
    scale = np.diag(cov).mean()
    return _solve(lambda w: w @ cov @ w / scale, len(cov), long_only, max_weight)


def mean_variance(mu, cov, risk_aversion: float = 2.5, long_only: bool = True,
                  max_weight: float | None = None) -> np.ndarray:
    """Fully invested weights maximising  w'mu - (risk_aversion / 2) w'Cov w."""
    mu, cov = np.asarray(mu, dtype=float), np.asarray(cov, dtype=float)
    scale = max(np.abs(mu).max(), 1e-12)
    return _solve(lambda w: -(w @ mu - risk_aversion / 2 * w @ cov @ w) / scale,
                  len(mu), long_only, max_weight)
