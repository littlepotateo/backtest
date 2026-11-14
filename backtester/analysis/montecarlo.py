"""Monte Carlo tests. Each variant answers a different question; see
docs/research/monte-carlo.md.

  reshuffle  - same trades in random order: how bad could the drawdown have been?
  bootstrap  - resampled daily returns in blocks: how uncertain are return and drawdown?
  skip       - randomly miss some trades: does the result lean on a few of them?
  synthetic  - re-run the strategy on resampled price histories (slow, opt-in).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtester.analysis.metrics import TRADING_DAYS
from backtester.analysis.optimize import daily_returns
from backtester.analysis.resample import (bootstrap_paths, optimal_block_length,
                                          stationary_bootstrap_indices)
from backtester.engine.backend import Runner
from backtester.engine.result import RunResult

PCTS = (5, 25, 50, 75, 95)


def _drawdowns(paths: np.ndarray) -> np.ndarray:
    """Max drawdown (negative fraction) of each row of cumulative wealth paths."""
    wealth = np.concatenate([np.ones((paths.shape[0], 1)), paths], axis=1)
    peaks = np.maximum.accumulate(wealth, axis=1)
    return (wealth / peaks - 1).min(axis=1)


def _summary(wealth: np.ndarray, actual_dd: float, ruin: float, years: float | None) -> dict:
    final = wealth[:, -1] - 1
    dd = _drawdowns(wealth)
    out = {
        "paths": int(len(wealth)),
        "total_return": {f"p{p}": float(np.percentile(final, p)) for p in PCTS},
        "max_drawdown": {f"p{p}": float(np.percentile(dd, 100 - p)) for p in PCTS},
        "probability_of_loss": float((final < 0).mean()),
        "risk_of_ruin": float((dd <= -abs(ruin)).mean()),
        "ruin_threshold": -abs(ruin),
        "probability_drawdown_worse_than_backtest": float((dd < actual_dd - 1e-12).mean()),
    }
    if years and years > 0:
        cagr = np.where(wealth[:, -1] > 0, wealth[:, -1] ** (1 / years) - 1, -1.0)
        out["annual_return"] = {f"p{p}": float(np.percentile(cagr, p)) for p in PCTS}
    return out


def trade_fractions(result: RunResult) -> np.ndarray:
    """Each closed trade's profit as a fraction of account equity just before it closed."""
    t = result.trades
    if t.empty:
        return np.array([])
    eq = result.equity
    pos = np.clip(eq.index.searchsorted(pd.DatetimeIndex(t["exit_time"]), side="right") - 1, 0, len(eq) - 1)
    at_exit = eq.to_numpy()[pos]
    return t["pnl"].to_numpy() / (at_exit - t["pnl"].to_numpy())


def monte_carlo(result: RunResult, n_paths: int = 5000, seed: int = 0, ruin: float = 0.5,
                skip_probability: float = 0.10) -> dict:
    rng = np.random.default_rng(seed)
    r = daily_returns(result).to_numpy()
    years = len(r) / TRADING_DAYS
    actual_wealth = np.cumprod(1 + r)[None, :]
    actual_dd = float(_drawdowns(actual_wealth)[0])
    out = {"seed": seed, "backtest_max_drawdown": actual_dd,
           "backtest_total_return": float(actual_wealth[0, -1] - 1)}

    block = optimal_block_length(r)
    boot = np.cumprod(1 + bootstrap_paths(r, n_paths, rng, block), axis=1)
    out["bootstrap"] = {**_summary(boot, actual_dd, ruin, years), "mean_block_days": block}
    step = max(1, boot.shape[1] // 200)
    out["bootstrap"]["fan"] = {f"p{p}": np.percentile(boot[:, ::step], p, axis=0).tolist() for p in PCTS}

    f = trade_fractions(result)
    out["trades"] = int(len(f))
    if len(f) >= 2:
        trade_dd = float(_drawdowns(np.cumprod(1 + f)[None, :])[0])
        shuffled = np.stack([np.cumprod(1 + rng.permutation(f)) for _ in range(n_paths)])
        out["reshuffle"] = _summary(shuffled, trade_dd, ruin, None)
        out["reshuffle"]["trade_sequence_drawdown"] = trade_dd
        keep = rng.random((n_paths, len(f))) >= skip_probability
        skipped = np.cumprod(1 + np.where(keep, f, 0.0), axis=1)
        out["skip"] = {**_summary(skipped, trade_dd, ruin, None), "skip_probability": skip_probability}
    return out


def synthetic_bars(data: dict[str, pd.DataFrame], rng: np.random.Generator,
                   block: float | None = None) -> dict[str, pd.DataFrame]:
    """A resampled price history for every symbol. Blocks of consecutive bars are drawn
    (the same blocks for all symbols, keeping their co-movement) and chained, so each
    bar keeps its real shape relative to the previous close. Timestamps are unchanged.
    Symbols must share a calendar."""
    symbols = list(data)
    n = len(data[symbols[0]])
    if any(len(data[s]) != n for s in symbols):
        raise ValueError("synthetic price paths need all symbols on the same calendar")
    if block is None:
        closes = data[symbols[0]]["close"].to_numpy()
        block = optimal_block_length(np.abs(np.diff(np.log(closes))))   # keep volatility clusters
    idx = stationary_bootstrap_indices(n - 1, block, rng) + 1          # bar 0 has no previous close
    out = {}
    for s in symbols:
        df = data[s]
        c = df["close"].to_numpy()
        prev = c[idx - 1]
        ratios = {k: df[k].to_numpy()[idx] / prev for k in ("open", "high", "low", "close")}
        new_close = c[0] * np.cumprod(ratios["close"])
        base = np.concatenate([[c[0]], new_close[:-1]])
        new = df.copy()
        for k in ("open", "high", "low"):
            new.iloc[1:, new.columns.get_loc(k)] = base * ratios[k]
        new.iloc[1:, new.columns.get_loc("close")] = new_close
        new.iloc[1:, new.columns.get_loc("volume")] = df["volume"].to_numpy()[idx]
        if "adj_factor" in new:
            new["adj_factor"] = 1.0 if (df["adj_factor"] == 1).all() else df["adj_factor"].to_numpy()
        out[s] = new
    return out


def synthetic_reruns(runner: Runner, params: dict | None = None, n_paths: int = 200,
                     seed: int = 0) -> dict:
    """Re-run the strategy on resampled price histories. Prices are made from the
    already-adjusted series, so adjustment is switched off for these runs."""
    rng = np.random.default_rng(seed)
    adj = {}
    for s, df in runner.data.items():
        d = df.copy()
        if runner.config.use_adjusted:
            for k in ("open", "high", "low", "close"):
                d[k] = d[k] * d["adj_factor"]
            d["adj_factor"] = 1.0
        adj[s] = d
    finals, dds = [], []
    for _ in range(n_paths):
        res = runner.run(params, data=synthetic_bars(adj, rng), use_adjusted=False)
        r = daily_returns(res).to_numpy()
        w = np.cumprod(1 + r)
        finals.append(w[-1] - 1)
        dds.append(float(_drawdowns(w[None, :])[0]))
    finals, dds = np.array(finals), np.array(dds)
    return {"paths": n_paths, "seed": seed,
            "total_return": {f"p{p}": float(np.percentile(finals, p)) for p in PCTS},
            "max_drawdown": {f"p{p}": float(np.percentile(dds, 100 - p)) for p in PCTS},
            "probability_of_loss": float((finals < 0).mean())}
