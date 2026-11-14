"""Core performance metrics, computed from a RunResult only.

Return-based statistics (volatility, Sharpe, Sortino) use one return per trading day,
whatever the bar size, so daily and intraday strategies are comparable.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from backtester.engine.result import RunResult

TRADING_DAYS = 252


def daily_equity(equity: pd.Series, timezone: str = "America/New_York") -> pd.Series:
    """Last account value of each trading day."""
    days = equity.index.tz_convert(timezone).date
    out = equity.groupby(days).last()
    out.index = pd.DatetimeIndex(out.index)
    return out


def max_drawdown(values: np.ndarray) -> float:
    """Largest peak-to-trough fall, as a negative fraction (0.0 if none)."""
    peaks = np.maximum.accumulate(values)
    return float((values / peaks - 1).min())


def longest_drawdown_days(equity: pd.Series) -> int:
    """Longest stretch, in calendar days, spent below a previous peak."""
    peaks = equity.cummax()
    longest, start = pd.Timedelta(0), None
    for t, under in (equity < peaks).items():
        if under and start is None:
            start = last_peak
        if not under:
            if start is not None:
                longest = max(longest, t - start)
                start = None
            last_peak = t
    if start is not None:
        longest = max(longest, equity.index[-1] - start)
    return int(longest.days)


def _clean(x):
    if isinstance(x, (float, np.floating)):
        return None if not math.isfinite(x) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def compute_metrics(result: RunResult, risk_free_rate: float = 0.0,
                    benchmark: pd.Series | None = None) -> dict:
    """Metrics for a run. `risk_free_rate` is annual. `benchmark` is an optional price
    series (e.g. the asset itself, for buy-and-hold) used for alpha and beta."""
    cfg = result.meta.get("config", {})
    initial = float(cfg.get("initial_cash", result.equity.iloc[0]))
    tz = cfg.get("timezone", "America/New_York")
    daily = daily_equity(result.equity, tz)
    values = np.concatenate([[initial], daily.to_numpy()])
    rets = values[1:] / values[:-1] - 1
    n = len(rets)
    years = n / TRADING_DAYS
    total = values[-1] / initial - 1
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else float("nan")
    rf_d = risk_free_rate / TRADING_DAYS
    sd = rets.std(ddof=1) if n > 1 else float("nan")
    vol = sd * math.sqrt(TRADING_DAYS)
    sharpe = (rets.mean() - rf_d) / sd * math.sqrt(TRADING_DAYS) if sd and sd > 0 else float("nan")
    downside = math.sqrt(np.mean(np.minimum(rets - rf_d, 0) ** 2)) if n else float("nan")
    sortino = (rets.mean() - rf_d) / downside * math.sqrt(TRADING_DAYS) if downside > 0 else float("nan")
    full = pd.concat([pd.Series([initial], index=[result.equity.index[0] - pd.Timedelta(seconds=1)]),
                      result.equity])
    mdd = max_drawdown(full.to_numpy())

    m = {
        "start": result.equity.index[0].isoformat(),
        "end": result.equity.index[-1].isoformat(),
        "trading_days": n,
        "initial_cash": initial,
        "final_equity": float(values[-1]),
        "total_return": total,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": mdd,
        "longest_drawdown_days": longest_drawdown_days(full),
        "calmar": cagr / abs(mdd) if mdd < 0 else float("nan"),
        "best_day": float(rets.max()) if n else float("nan"),
        "worst_day": float(rets.min()) if n else float("nan"),
    }

    t = result.trades
    wins, losses = t[t["pnl"] > 0]["pnl"], t[t["pnl"] <= 0]["pnl"]
    m.update({
        "trades": int(len(t)),
        "win_rate": len(wins) / len(t) if len(t) else float("nan"),
        "profit_factor": wins.sum() / abs(losses.sum()) if losses.sum() < 0 else float("nan"),
        "expectancy": float(t["pnl"].mean()) if len(t) else float("nan"),
        "avg_win": float(wins.mean()) if len(wins) else float("nan"),
        "avg_loss": float(losses.mean()) if len(losses) else float("nan"),
        "avg_trade_return": float(t["return"].mean()) if len(t) else float("nan"),
    })

    f = result.fills
    traded = float((f["qty"].abs() * f["price"]).sum())
    m.update({
        "fills": int(len(f)),
        "total_commission": float(f["commission"].sum()),
        "total_slippage": float(f["slippage_cost"].sum()),
        "turnover_per_year": traded / float(result.equity.mean()) / years if years > 0 else float("nan"),
        "time_in_market": float((result.gross_exposure > 0).mean()),
        "avg_gross_exposure": float(result.gross_exposure.mean()),
    })

    if benchmark is not None and len(benchmark) > 1:
        b = benchmark.copy()
        b.index = pd.DatetimeIndex(pd.to_datetime(b.index, utc=True))
        b = daily_equity(b, tz).reindex(daily.index).ffill().dropna()
        if len(b) > 2:
            b_rets = b.pct_change().dropna()
            s_rets = daily.pct_change().reindex(b_rets.index).dropna()
            b_rets = b_rets.reindex(s_rets.index)
            b_total = b.iloc[-1] / b.iloc[0] - 1
            b_years = (len(b) - 1) / TRADING_DAYS
            var = b_rets.var(ddof=1)
            beta = s_rets.cov(b_rets) / var if var > 0 else float("nan")
            alpha = ((s_rets.mean() - rf_d) - beta * (b_rets.mean() - rf_d)) * TRADING_DAYS
            m.update({
                "benchmark_total_return": float(b_total),
                "benchmark_cagr": float((1 + b_total) ** (1 / b_years) - 1) if b_years > 0 else float("nan"),
                "benchmark_max_drawdown": max_drawdown(b.to_numpy()),
                "beta": float(beta),
                "alpha_annual": float(alpha),
            })
    return {k: _clean(v) for k, v in m.items()}
