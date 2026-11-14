"""Kelly criterion: how large to trade for the fastest long-run growth, and how costly
over-betting is. See docs/research/kelly.md.

All results are expressed as a multiple of the position size used in the backtest
("1.0" = trade exactly as backtested, "0.5" = half the size, "2.0" = double).
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize_scalar

from backtester.analysis.metrics import TRADING_DAYS
from backtester.analysis.montecarlo import trade_fractions
from backtester.analysis.optimize import daily_returns
from backtester.analysis.resample import bootstrap_paths
from backtester.engine.result import RunResult


def kelly_binary(p: float, b: float) -> float:
    """Kelly fraction for a bet won with probability `p` paying `b` to 1."""
    if b <= 0:
        return 0.0
    return max(p - (1 - p) / b, 0.0)


def kelly_continuous(mean_excess: float, variance: float) -> float:
    """Kelly leverage for a return stream: mean excess return over variance."""
    return max(mean_excess / variance, 0.0) if variance > 0 else 0.0


def growth_rate(returns: np.ndarray, f: float) -> float:
    """Average log growth per period when every return is scaled by `f`."""
    x = 1 + f * returns
    return float(np.mean(np.log(x))) if (x > 0).all() else -math.inf


def kelly_empirical(returns) -> float:
    """The scale `f` that maximises average log growth of the observed returns."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) == 0 or r.mean() <= 0:
        return 0.0
    worst = r.min()
    if worst >= 0:
        return math.inf                      # no losing outcome observed: unbounded
    f_max = -1 / worst * (1 - 1e-9)
    res = minimize_scalar(lambda f: -growth_rate(r, f), bounds=(0.0, f_max), method="bounded",
                          options={"xatol": 1e-7})
    return float(res.x)


def kelly_analysis(result: RunResult, risk_free_rate: float = 0.0, n_boot: int = 500,
                   seed: int = 0, max_leverage: float | None = None) -> dict:
    r = daily_returns(result).to_numpy()
    rf = risk_free_rate / TRADING_DAYS
    excess = r - rf
    out: dict = {"unit": "multiple of the backtested position size"}

    f_cont = kelly_continuous(excess.mean(), excess.var(ddof=1)) if len(r) > 1 else 0.0
    f_emp = kelly_empirical(excess)
    out["from_daily_returns"] = {"continuous": f_cont,
                                 "empirical": None if math.isinf(f_emp) else f_emp}

    f = trade_fractions(result)
    if len(f):
        wins, losses = f[f > 0], f[f <= 0]
        p = len(wins) / len(f)
        b = wins.mean() / abs(losses.mean()) if len(wins) and len(losses) and losses.mean() < 0 else 0.0
        size = abs(losses.mean()) if len(losses) and losses.mean() < 0 else float("nan")
        f_tr = kelly_empirical(f)
        out["from_trades"] = {
            "win_rate": p, "payoff_ratio": float(b),
            "binary_fraction_of_capital_at_risk": kelly_binary(p, b),
            "binary_as_size_multiple": float(kelly_binary(p, b) / size) if size and np.isfinite(size) and size > 0 else None,
            "empirical": None if math.isinf(f_tr) else f_tr, "trades": int(len(f)),
        }

    point = f_emp if not math.isinf(f_emp) else f_cont
    out["point_estimate"] = point
    if point <= 0:
        out["edge"] = False
        out["recommended"] = 0.0
        out["note"] = "No positive edge in the backtest: there is nothing to size."
        return out
    out["edge"] = True

    rng = np.random.default_rng(seed)
    boots = np.array([kelly_empirical(path) for path in bootstrap_paths(excess, n_boot, rng)])
    boots = np.where(np.isinf(boots), np.nan, boots)
    out["bootstrap"] = {f"p{p}": float(np.nanpercentile(boots, p)) for p in (5, 25, 50, 75, 95)}
    out["probability_no_edge"] = float(np.mean(boots == 0))

    recommended = min(0.5 * point, out["bootstrap"]["p25"])
    exposure = float(result.gross_exposure.max())
    cap = None
    if max_leverage and exposure > 0:
        cap = max_leverage / exposure
        recommended = min(recommended, cap)
    out["recommended"] = float(max(recommended, 0.0))
    out["leverage_cap_multiple"] = cap
    out["recommended_rule"] = "the smaller of half the point estimate and the 25th-percentile bootstrap estimate"

    grid = np.linspace(0, min(2.5 * point, -1 / excess.min() * 0.999 if excess.min() < 0 else 2.5 * point), 51)
    out["curve"] = {"multiple": grid.tolist(),
                    "annual_log_growth": [growth_rate(excess, f) * TRADING_DAYS for f in grid]}
    out["growth_at"] = {name: growth_rate(excess, m * point) * TRADING_DAYS
                        for name, m in (("quarter_kelly", 0.25), ("half_kelly", 0.5),
                                        ("full_kelly", 1.0), ("as_backtested", 1.0 / point))}
    out["note"] = ("Backtest returns are optimistic, so these are upper bounds. "
                   "Over-betting is far more damaging than under-betting.")
    return out
