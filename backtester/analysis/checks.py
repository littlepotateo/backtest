"""Checks that should pass before a backtest result is taken seriously.
See docs/research/regimes-costs-lookahead.md."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtester.engine.backend import Runner
from backtester.engine.result import RunResult


def lookahead_test(runner: Runner, params: dict | None = None,
                   cut_fractions: tuple = (0.5, 0.7, 0.9)) -> dict:
    """Truncation test: cut the data off at several dates and re-run. Every order placed
    up to a cut-off must be identical to the full run's. If not, the strategy's decisions
    depended on data from after the cut-off.

    Limit: this catches look-ahead through the price data the engine supplies. It cannot
    see a strategy that loads its own data from somewhere else."""
    full = runner.run(params)
    timeline = full.equity.index
    cuts, passed, first_problem = [], True, None
    for frac in cut_fractions:
        cut = timeline[min(int(len(timeline) * frac), len(timeline) - 1)]
        data = {s: df[df.index <= cut] for s, df in runner.data.items()}
        short = runner.run(params, data=data, end=None)
        a = (full.orders[full.orders["time"] <= cut] if len(full.orders) else full.orders).reset_index(drop=True)
        b = short.orders.reset_index(drop=True)
        same = len(a) == len(b) and a.equals(b)
        if same:
            fa = (full.fills[full.fills["time"] <= cut] if len(full.fills) else full.fills).reset_index(drop=True)
            same = len(fa) == len(short.fills) and np.allclose(
                fa[["qty", "price"]].to_numpy(float), short.fills[["qty", "price"]].to_numpy(float))
        cuts.append({"cutoff": cut.isoformat(), "orders_checked": int(len(a)), "identical": bool(same)})
        if not same and first_problem is None:
            n = min(len(a), len(b))
            diff = next((i for i in range(n) if not a.iloc[i].equals(b.iloc[i])), n)
            first_problem = {"cutoff": cut.isoformat(), "first_differing_order": int(diff),
                             "full_run_orders": int(len(a)), "truncated_run_orders": int(len(b))}
            passed = False
    return {"passed": passed, "cuts": cuts, "problem": first_problem,
            "same_bar_fills": runner.config.fill == "close"}


def data_quality(data: dict[str, pd.DataFrame], interval: str) -> dict:
    out = {}
    for s, df in data.items():
        gaps = df.index.to_series().diff().dropna()
        logret = np.log(df["close"]).diff().dropna()
        if len(gaps) and interval != "1d" and interval != "1w":
            logret = logret[(gaps <= gaps.median() * 1.5).to_numpy()]   # not across overnight breaks
        sd = logret.std()
        day_gap = gaps.max().days if len(gaps) else 0
        issues = []
        spikes = int((logret.abs() > 10 * sd).sum()) if sd > 0 else 0
        if spikes:
            issues.append(f"{spikes} bar(s) moved more than 10 standard deviations "
                          "(check these are real market moves)")
        bad = int(((df["high"] < df[["open", "close"]].max(axis=1) - 1e-9)
                   | (df["low"] > df[["open", "close"]].min(axis=1) + 1e-9)).sum())
        if bad:
            issues.append(f"{bad} bar(s) where high/low do not contain open/close")
        if day_gap > 7:
            issues.append(f"longest gap between bars is {day_gap} days")
        zero_vol = float((df["volume"] == 0).mean())
        if zero_vol > 0.05:
            issues.append(f"{zero_vol:.0%} of bars have zero volume")
        out[s] = {"bars": int(len(df)), "start": df.index[0].isoformat(), "end": df.index[-1].isoformat(),
                  "longest_gap_days": int(day_gap), "issues": issues}
    return out


def trade_checks(result: RunResult) -> dict:
    t = result.trades
    n = len(t)
    out = {"trades": int(n)}
    if n == 0:
        return out
    pnl = t["pnl"].sort_values(ascending=False)
    gross_profit = float(pnl[pnl > 0].sum())
    top = max(1, int(np.ceil(n * 0.05)))
    total = float(pnl.sum())
    out.update({
        "net_profit_from_trades": total,
        "top_5pct_trades": top,
        "top_5pct_share_of_gross_profit": float(pnl.iloc[:top].clip(lower=0).sum() / gross_profit) if gross_profit > 0 else None,
        "profit_without_best_trade": float(total - pnl.iloc[0]),
        "best_trade": float(pnl.iloc[0]), "worst_trade": float(pnl.iloc[-1]),
    })
    return out
