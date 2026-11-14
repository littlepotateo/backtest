"""In-sample / out-of-sample split, walk-forward optimisation and parameter sensitivity.

See docs/research/walk-forward.md. The parameters for each out-of-sample segment are
chosen using only earlier data; the out-of-sample curve comes from a single engine run
in which the parameters switch at the segment boundaries, so positions carry over.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtester.analysis.optimize import annual_return, daily_returns, sharpe
from backtester.engine.backend import Runner

MIN_TRADES_PER_WINDOW = 10


def make_windows(n_days: int, is_days: int | None = None, oos_days: int | None = None,
                 mode: str = "rolling", min_windows: int = 5) -> list[tuple[int, int, int, int]]:
    """Window boundaries as day positions: (is_start, is_end, oos_start, oos_end), end
    exclusive. Defaults: one-year out-of-sample segments with four years in-sample,
    shrunk proportionally if that would give fewer than `min_windows`."""
    if mode not in ("rolling", "anchored"):
        raise ValueError("mode must be 'rolling' or 'anchored'")
    if oos_days is None:
        oos_days = min(252, n_days // (4 + min_windows))
    if is_days is None:
        is_days = 4 * oos_days
    if oos_days < 5 or is_days + oos_days > n_days:
        raise ValueError("not enough data for walk-forward windows")
    windows, k = [], 0
    while True:
        oos_start = is_days + k * oos_days
        oos_end = min(oos_start + oos_days, n_days)
        if oos_start >= n_days or oos_end - oos_start < oos_days / 2:
            break
        is_start = 0 if mode == "anchored" else k * oos_days
        windows.append((is_start, oos_start, oos_start, oos_end))
        k += 1
    return windows


def _first_bar_on(result_index: pd.DatetimeIndex, day, tz: str) -> pd.Timestamp:
    days = result_index.tz_convert(tz).normalize().tz_localize(None)
    return result_index[np.searchsorted(days, pd.Timestamp(day), side="left")]


def walk_forward(runner: Runner, grid_result: dict, is_days: int | None = None,
                 oos_days: int | None = None, mode: str = "rolling") -> dict:
    returns: pd.DataFrame = grid_result["returns"]
    configs = grid_result["configs"]
    days = returns.index
    windows = make_windows(len(days), is_days, oos_days, mode)
    tz = runner.config.timezone

    chosen, schedule_days = [], []
    for is_start, is_end, oos_start, _ in windows:
        scores = returns.iloc[is_start:is_end].apply(sharpe).fillna(-np.inf)
        best = int(scores.idxmax())
        chosen.append(best)
        schedule_days.append(days[oos_start])

    # one run over the whole out-of-sample span, switching parameters at each boundary
    probe = runner.run(configs[chosen[0]], start=str(schedule_days[0].date()))
    schedule = [(_first_bar_on(probe.equity.index, d, tz), configs[c])
                for d, c in zip(schedule_days, chosen)]
    oos_run = runner.run(schedule=schedule, start=str(schedule_days[0].date())) \
        if len(set(chosen)) > 1 else probe
    oos = daily_returns(oos_run)
    trade_days = pd.DatetimeIndex(oos_run.trades["exit_time"]).tz_convert(tz).normalize().tz_localize(None) \
        if len(oos_run.trades) else pd.DatetimeIndex([])

    rows = []
    for (is_start, is_end, oos_start, oos_end), best in zip(windows, chosen):
        is_r = returns[best].iloc[is_start:is_end]
        seg = oos[(oos.index >= days[oos_start]) & (oos.index <= days[oos_end - 1])]
        n_trades = int(((trade_days >= days[oos_start]) & (trade_days <= days[oos_end - 1])).sum())
        rows.append({
            "is_start": str(days[is_start].date()), "is_end": str(days[is_end - 1].date()),
            "oos_start": str(days[oos_start].date()), "oos_end": str(days[oos_end - 1].date()),
            "params": configs[best],
            "is_sharpe": sharpe(is_r), "oos_sharpe": sharpe(seg),
            "is_annual_return": annual_return(is_r), "oos_annual_return": annual_return(seg),
            "oos_return": float(np.prod(1 + seg.to_numpy()) - 1), "oos_trades": n_trades,
            "too_few_trades": n_trades < MIN_TRADES_PER_WINDOW,
        })
    table = pd.DataFrame(rows)
    is_ret, oos_ret = table["is_annual_return"].mean(), annual_return(oos)
    is_sh, oos_sh = table["is_sharpe"].mean(), sharpe(oos)

    stability = {}
    for name, values in runner.strategy_cls.param_grid.items():
        picks = [configs[c][name] for c in chosen]
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in list(values) + picks):
            span = max(values) - min(values)
            stability[name] = float(np.std(picks) / span) if span else 0.0

    return {
        "mode": mode, "windows": table,
        "is_days": windows[0][1] - windows[0][0], "oos_days": windows[0][3] - windows[0][2],
        "oos_returns": oos, "oos_equity": oos_run.equity,
        "oos_total_return": float(np.prod(1 + oos.to_numpy()) - 1),
        "oos_annual_return": oos_ret, "oos_sharpe": oos_sh,
        "is_annual_return_mean": float(is_ret), "is_sharpe_mean": float(is_sh),
        "wfe_return": float(oos_ret / is_ret) if is_ret > 0 else None,
        "wfe_sharpe": float(oos_sh / is_sh) if is_sh > 0 and np.isfinite(oos_sh) else None,
        "windows_profitable": float((table["oos_return"] > 0).mean()),
        "windows_with_too_few_trades": int(table["too_few_trades"].sum()),
        "distinct_params_chosen": len(set(chosen)),
        "param_instability": stability,
    }


def in_out_of_sample(runner: Runner, grid_result: dict, in_sample_fraction: float = 0.7) -> dict:
    """Pick the best configuration on the first part of the period, then run it on the rest."""
    returns, configs = grid_result["returns"], grid_result["configs"]
    cut = int(len(returns) * in_sample_fraction)
    if cut < 20 or len(returns) - cut < 20:
        raise ValueError("not enough data for an in-sample / out-of-sample split")
    scores = returns.iloc[:cut].apply(sharpe).fillna(-np.inf)
    best = int(scores.idxmax())
    split_day = returns.index[cut]
    oos = daily_returns(runner.run(configs[best], start=str(split_day.date())))
    is_sharpe, oos_sharpe = float(scores[best]), sharpe(oos)
    return {
        "split_date": str(split_day.date()), "params": configs[best],
        "is_sharpe": is_sharpe, "oos_sharpe": oos_sharpe,
        "is_annual_return": annual_return(returns[best].iloc[:cut]),
        "oos_annual_return": annual_return(oos),
        "sharpe_retained": float(oos_sharpe / is_sharpe) if is_sharpe > 0 and np.isfinite(oos_sharpe) else None,
    }


def sensitivity(strategy_cls, grid_result: dict, objective: str = "sharpe") -> dict:
    """How much the objective depends on the exact parameters chosen.

    plateau_ratio = median objective of the best configuration's grid neighbours divided
    by the best objective. Near 1 means a broad plateau; small means a lucky spike."""
    table, configs = grid_result["table"], grid_result["configs"]
    grid = strategy_cls.param_grid
    best = grid_result["best"]
    best_value = float(table.loc[best, objective])

    def is_neighbour(a: dict, b: dict) -> bool:
        diff = [k for k in grid if a[k] != b[k]]
        if len(diff) != 1:
            return False
        values = list(grid[diff[0]])
        return abs(values.index(a[diff[0]]) - values.index(b[diff[0]])) == 1

    neighbours = [float(table.loc[i, objective]) for i, c in enumerate(configs)
                  if i != best and is_neighbour(configs[best], c)]
    neighbours = [v for v in neighbours if np.isfinite(v)]
    values = table[objective].to_numpy(dtype=float)
    out = {
        "objective": objective, "best_params": configs[best], "best": best_value,
        "neighbours": neighbours,
        "plateau_ratio": float(np.median(neighbours) / best_value) if neighbours and best_value > 0 else None,
        "share_of_grid_positive": float(np.mean(values[np.isfinite(values)] > 0)),
        "grid_median": float(np.nanmedian(values)),
        "table": table,
    }
    varying = [k for k, v in grid.items() if len(v) > 1]
    if len(varying) == 2:
        out["heatmap"] = table.pivot_table(index=varying[0], columns=varying[1], values=objective)
    return out
