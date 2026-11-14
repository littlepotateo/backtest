"""Black-Scholes-Merton prices and greeks with a continuous dividend yield.
See docs/research/options-pricing.md. All functions accept arrays.

T is in years; `right` is "C" or "P". US equity options are American; this prices them
as European and the engine handles early assignment by rule.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

MIN_T = 1e-8


def _d1_d2(s, k, t, r, q, sigma):
    t = np.maximum(t, MIN_T)
    vol = sigma * np.sqrt(t)
    d1 = (np.log(s / k) + (r - q + 0.5 * sigma ** 2) * t) / vol
    return d1, d1 - vol


def intrinsic(s, k, right: str):
    return np.maximum(s - k, 0.0) if right == "C" else np.maximum(k - s, 0.0)


def price(s, k, t, r, q, sigma, right: str):
    """Option value. At or after expiry (t <= 0) this is the intrinsic value."""
    s, k, t, sigma = (np.asarray(x, dtype=float) for x in (s, k, t, sigma))
    d1, d2 = _d1_d2(s, k, t, r, q, sigma)
    tt = np.maximum(t, MIN_T)
    if right == "C":
        v = s * np.exp(-q * tt) * norm.cdf(d1) - k * np.exp(-r * tt) * norm.cdf(d2)
    elif right == "P":
        v = k * np.exp(-r * tt) * norm.cdf(-d2) - s * np.exp(-q * tt) * norm.cdf(-d1)
    else:
        raise ValueError("right must be 'C' or 'P'")
    out = np.where(t <= 0, intrinsic(s, k, right), v)
    return float(out) if out.ndim == 0 else out


def greeks(s, k, t, r, q, sigma, right: str) -> dict:
    """delta, gamma, vega (per 1.00 of volatility) and theta (per year), per share."""
    s, k, t, sigma = (np.asarray(x, dtype=float) for x in (s, k, t, sigma))
    tt = np.maximum(t, MIN_T)
    d1, d2 = _d1_d2(s, k, t, r, q, sigma)
    pdf, eq, er = norm.pdf(d1), np.exp(-q * tt), np.exp(-r * tt)
    gamma = eq * pdf / (s * sigma * np.sqrt(tt))
    vega = s * eq * pdf * np.sqrt(tt)
    decay = -s * eq * pdf * sigma / (2 * np.sqrt(tt))
    if right == "C":
        delta = eq * norm.cdf(d1)
        theta = decay - r * k * er * norm.cdf(d2) + q * s * eq * norm.cdf(d1)
    elif right == "P":
        delta = -eq * norm.cdf(-d1)
        theta = decay + r * k * er * norm.cdf(-d2) - q * s * eq * norm.cdf(-d1)
    else:
        raise ValueError("right must be 'C' or 'P'")
    live = t > 0
    expired_delta = np.where(s > k, 1.0, 0.0) if right == "C" else np.where(s < k, -1.0, 0.0)
    out = {"delta": np.where(live, delta, expired_delta), "gamma": np.where(live, gamma, 0.0),
           "vega": np.where(live, vega, 0.0), "theta": np.where(live, theta, 0.0)}
    return {name: (float(v) if v.ndim == 0 else v) for name, v in out.items()}


def implied_vol(target: float, s: float, k: float, t: float, r: float, q: float, right: str,
                lo: float = 0.01, hi: float = 5.0) -> float:
    """Volatility at which the model price equals `target` (NaN if none in [lo, hi])."""
    f = lambda v: price(s, k, t, r, q, v, right) - target  # noqa: E731
    if t <= 0 or f(lo) > 0 or f(hi) < 0:
        return float("nan")
    return float(brentq(f, lo, hi, xtol=1e-10))
