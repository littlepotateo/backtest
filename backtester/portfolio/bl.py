"""Black-Litterman: blend the returns implied by a reference portfolio with your own
views, each held with a stated confidence. See docs/research/portfolio-allocation.md.

All returns, covariances and view sizes must be in the same units (e.g. all annual).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from backtester.portfolio.weights import mean_variance


@dataclass
class View:
    """A view on expected returns.

    absolute:  View({"EFA": 1}, 0.0525)               "EFA will return 5.25%"
    relative:  View({"SPY": 1, "AGG": -1}, 0.03)      "SPY will beat AGG by 3%"
    For a relative view the positive weights should sum to 1 and the negative to -1.
    `confidence` is between 0 (ignore the view) and 1 (certain)."""
    weights: dict
    value: float
    confidence: float = 0.5


def implied_returns(cov, market_weights, risk_aversion: float) -> np.ndarray:
    """Returns under which the reference portfolio would be optimal:  delta * Cov * w."""
    return risk_aversion * np.asarray(cov, dtype=float) @ np.asarray(market_weights, dtype=float)


def implied_risk_aversion(market_mean_excess: float, market_variance: float,
                          lo: float = 1.0, hi: float = 10.0) -> float:
    """delta = market excess return / market variance, kept within sensible bounds."""
    if market_variance <= 0:
        return 2.5
    return float(min(max(market_mean_excess / market_variance, lo), hi))


def view_matrices(views: list[View], symbols: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(P, Q, confidences) for a list of views over `symbols`."""
    p = np.zeros((len(views), len(symbols)))
    for i, v in enumerate(views):
        for sym, w in v.weights.items():
            if sym not in symbols:
                raise KeyError(f"view refers to {sym}, which is not in the universe")
            p[i, symbols.index(sym)] = w
        if not 0 <= v.confidence <= 1:
            raise ValueError("view confidence must be between 0 and 1")
    return p, np.array([v.value for v in views], dtype=float), np.array([v.confidence for v in views])


def omega_he_litterman(p, cov, tau: float) -> np.ndarray:
    """View uncertainty proportional to the variance of each view portfolio."""
    return np.diag(np.diag(tau * p @ cov @ p.T))


def omega_from_confidence(p, cov, tau: float, confidences) -> np.ndarray:
    """Closed-form shortcut for Idzorek's confidence method (as in Walters 2014 and
    PyPortfolioOpt):  omega_k = tau * (1 - c) / c * p_k Cov p_k'.
    Confidence 0.5 gives the He-Litterman value; 1 gives 0 (certain); 0 gives a
    very large number (ignored)."""
    base = np.diag(p @ cov @ p.T)
    c = np.asarray(confidences, dtype=float)
    alpha = np.where(c > 0, (1 - c) / np.where(c > 0, c, 1.0), 1e6 / tau)
    return np.diag(tau * alpha * base)


def posterior(pi, cov, p, q, omega, tau: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """Posterior expected returns and the covariance to optimise with (Cov + M)."""
    pi, cov = np.asarray(pi, dtype=float), np.asarray(cov, dtype=float)
    if len(q) == 0:
        return pi.copy(), (1 + tau) * cov
    ts_pt = tau * cov @ p.T
    a = p @ ts_pt + omega
    mu = pi + ts_pt @ np.linalg.solve(a, q - p @ pi)
    m = tau * cov - ts_pt @ np.linalg.solve(a, ts_pt.T)
    return mu, cov + m


def unconstrained_weights(mu, cov, risk_aversion: float) -> np.ndarray:
    """(delta * Cov)^-1 mu. Not normalised: the remainder is cash or borrowing."""
    return np.linalg.solve(risk_aversion * np.asarray(cov, dtype=float), np.asarray(mu, dtype=float))


@dataclass
class BLResult:
    symbols: list[str]
    prior_returns: np.ndarray
    posterior_returns: np.ndarray
    weights: np.ndarray
    prior_weights: np.ndarray
    risk_aversion: float
    tau: float
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        r = lambda a: {s: float(x) for s, x in zip(self.symbols, a)}  # noqa: E731
        return {"prior_returns": r(self.prior_returns), "posterior_returns": r(self.posterior_returns),
                "weights": r(self.weights), "prior_weights": r(self.prior_weights),
                "risk_aversion": self.risk_aversion, "tau": self.tau, "notes": self.notes}


def black_litterman(symbols: list[str], cov, prior_weights, views: list[View], *,
                    risk_aversion: float = 2.5, tau: float = 0.05, omega: str = "confidence",
                    long_only: bool = True, max_weight: float | None = 0.4,
                    equilibrium_prior: bool = True) -> BLResult:
    """Posterior returns and constrained, fully invested weights.

    `prior_weights` is the reference portfolio (market-capitalisation weights for a true
    equilibrium prior). With no views and no binding constraints the result is the
    reference portfolio itself."""
    cov = np.asarray(cov, dtype=float)
    w_ref = np.asarray(prior_weights, dtype=float)
    w_ref = w_ref / w_ref.sum()
    pi = implied_returns(cov, w_ref, risk_aversion)
    p, q, conf = view_matrices(views, symbols)
    if omega not in ("confidence", "he_litterman"):
        raise ValueError("omega must be 'confidence' or 'he_litterman'")
    om = omega_from_confidence(p, cov, tau, conf) if omega == "confidence" else omega_he_litterman(p, cov, tau)
    mu, _ = posterior(pi, cov, p, q, om, tau)
    # optimise with Cov (not Cov + M) so that no views returns exactly the reference
    # portfolio; this is also what reproduces Idzorek's published example
    weights = mean_variance(mu, cov, risk_aversion, long_only, max_weight)
    notes = []
    if not equilibrium_prior:
        notes.append("The reference portfolio is not market-capitalisation weights, so the prior "
                     "is not a market equilibrium.")
    if max_weight is not None and (weights >= max_weight - 1e-6).any():
        notes.append(f"Some weights are at the {max_weight:.0%} cap.")
    return BLResult(list(symbols), pi, mu, weights, w_ref, risk_aversion, tau, notes)
