"""Where does the strategy make its money? Performance split by market regime.

Regimes are labelled from the benchmark using only data up to the previous day, so a
day's label never depends on that day's (or any later) prices.
See docs/research/regimes-costs-lookahead.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtester.analysis.metrics import daily_equity, max_drawdown
from backtester.analysis.optimize import annual_return, daily_returns, sharpe
from backtester.engine.result import RunResult

MIN_DAYS = 20


def regime_labels(benchmark_close: pd.Series, timezone: str = "America/New_York") -> pd.DataFrame:
    """Daily labels (trend, volatility, drawdown, year) indexed by date."""
    b = benchmark_close.copy()
    b.index = pd.DatetimeIndex(pd.to_datetime(b.index, utc=True))
    c = daily_equity(b, timezone)
    ret = c.pct_change()
    sma = c.rolling(200).mean()
    trend = pd.Series(np.where(c > sma, "bull", "bear"), index=c.index).where(sma.notna(), "unknown")
    rv = ret.rolling(21).std()
    lo, hi = rv.rolling(252).quantile(1 / 3), rv.rolling(252).quantile(2 / 3)
    vol = pd.Series(np.where(rv <= lo, "low", np.where(rv >= hi, "high", "mid")), index=c.index) \
        .where(hi.notna(), "unknown")
    dd = pd.Series(np.where(c / c.cummax() - 1 < -0.10, "in drawdown", "normal"), index=c.index)
    labels = pd.DataFrame({"trend": trend, "volatility": vol, "drawdown": dd}).shift(1).fillna("unknown")
    labels["year"] = labels.index.year.astype(str)
    return labels


def regime_breakdown(result: RunResult, benchmark_close: pd.Series) -> dict:
    tz = result.meta.get("config", {}).get("timezone", "America/New_York")
    r = daily_returns(result)
    labels = regime_labels(benchmark_close, tz).reindex(r.index).fillna("unknown")
    total_log = float(np.log1p(r).sum())
    trades = result.trades
    entry_days = pd.DatetimeIndex(trades["entry_time"]).tz_convert(tz).normalize().tz_localize(None) \
        if len(trades) else pd.DatetimeIndex([])
    out = {}
    for dim in list(labels.columns):
        rows = []
        for name, idx in labels.groupby(dim).groups.items():
            seg = r.loc[idx]
            mask = labels[dim].reindex(entry_days).to_numpy() == name if len(trades) else np.array([], bool)
            pnl = trades["pnl"].to_numpy()[mask] if len(trades) else np.array([])
            rows.append({
                "regime": name, "days": int(len(seg)), "share_of_time": float(len(seg) / len(r)),
                "total_return": float(np.prod(1 + seg.to_numpy()) - 1),
                "annual_return": annual_return(seg) if len(seg) >= MIN_DAYS else None,
                "sharpe": sharpe(seg) if len(seg) >= MIN_DAYS else None,
                "max_drawdown": max_drawdown(np.concatenate([[1.0], np.cumprod(1 + seg.to_numpy())])),
                "share_of_profit": float(np.log1p(seg).sum() / total_log) if total_log > 0 else None,
                "trades": int(mask.sum()),
                "win_rate": float((pnl > 0).mean()) if len(pnl) else None,
                "too_little_data": bool(len(seg) < MIN_DAYS),
            })
        out[dim] = rows
    out["labelled_share"] = float((labels["trend"] != "unknown").mean())
    seen = set(labels["trend"]) - {"unknown"}
    out["missing"] = [f"no {name} market in the sample" for name in ("bull", "bear") if name not in seen]
    return out
