"""Resampling tools shared by the Monte Carlo, Kelly and overfitting tests.

Stationary bootstrap: Politis & Romano (1994). Automatic block length: Politis & White
(2004) with the Patton, Politis & White (2009) correction. See docs/research/monte-carlo.md.
"""

from __future__ import annotations

import math

import numpy as np


def stationary_bootstrap_indices(n: int, block: float, rng: np.random.Generator,
                                 size: int | None = None) -> np.ndarray:
    """Indices into a series of length `n`: random-length blocks (mean length `block`)
    of consecutive observations, wrapping around the end."""
    size = n if size is None else size
    block = max(float(block), 1.0)
    new = rng.random(size) < 1.0 / block
    new[0] = True
    group = np.cumsum(new) - 1
    starts = rng.integers(0, n, size=int(group[-1]) + 1)
    first = np.flatnonzero(new)
    offset = np.arange(size) - first[group]
    return (starts[group] + offset) % n


def optimal_block_length(x) -> float:
    """Mean block length for the stationary bootstrap of series `x`."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 20 or x.std() == 0:
        return 1.0
    x = x - x.mean()
    # Details (lag window, fallback) follow Patton's reference code as implemented in
    # the `arch` package, which the tests compare against.
    k_n = max(5, int(math.log10(n)))
    m_max = math.ceil(math.sqrt(n)) + k_n
    b_max = math.ceil(min(3 * math.sqrt(n), n / 3))
    cov = np.array([np.dot(x[: n - k], x[k:]) / n for k in range(m_max + 1)])
    rho = cov / cov[0]
    threshold = 2 * math.sqrt(math.log10(n) / n)
    small = np.abs(rho) < threshold
    m_hat = None
    for k in range(1, m_max - k_n + 2):          # first lag from which k_n lags are all small
        if small[k:k + k_n].all():
            m_hat = k
            break
    m = min(2 * m_hat, m_max) if m_hat is not None else m_max
    lags = np.arange(1, m + 1)
    t = lags / m
    kernel = np.where(t <= 0.5, 1.0, 2 * (1 - t))
    g = 2 * np.sum(kernel * lags * cov[1:m + 1])
    long_run = cov[0] + 2 * np.sum(kernel * cov[1:m + 1])
    d_sb = 2 * long_run ** 2
    if d_sb <= 0 or g == 0:
        return 1.0
    b = (2 * g ** 2 / d_sb) ** (1 / 3) * n ** (1 / 3)
    return float(min(max(b, 1.0), b_max))


def bootstrap_paths(returns, n_paths: int, rng: np.random.Generator,
                    block: float | None = None) -> np.ndarray:
    """`n_paths` resampled copies of a return series (rows), same length as the original."""
    r = np.asarray(returns, dtype=float)
    block = optimal_block_length(r) if block is None else block
    return np.stack([r[stationary_bootstrap_indices(len(r), block, rng)] for _ in range(n_paths)])
