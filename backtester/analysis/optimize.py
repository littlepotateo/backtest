"""Parameter grid search and the trial ledger.

Every configuration ever evaluated is recorded, because the deflated Sharpe ratio needs
an honest count of how many variants were tried (docs/research/overfitting-statistics.md).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backtester.analysis.metrics import TRADING_DAYS, daily_equity, max_drawdown
from backtester.engine.backend import Runner
from backtester.engine.result import RunResult


def daily_returns(result: RunResult) -> pd.Series:
    """One return per trading day, the first measured from the starting cash."""
    cfg = result.meta.get("config", {})
    daily = daily_equity(result.equity, cfg.get("timezone", "America/New_York"))
    start = float(cfg.get("initial_cash", daily.iloc[0]))
    values = np.concatenate([[start], daily.to_numpy()])
    return pd.Series(values[1:] / values[:-1] - 1, index=daily.index)


def sharpe(returns, periods: int = TRADING_DAYS) -> float:
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        return float("nan")
    sd = r.std(ddof=1)
    return float(r.mean() / sd * math.sqrt(periods)) if sd > 0 else float("nan")


def annual_return(returns, periods: int = TRADING_DAYS) -> float:
    r = np.asarray(returns, dtype=float)
    if len(r) == 0:
        return float("nan")
    total = float(np.prod(1 + r))
    return total ** (periods / len(r)) - 1 if total > 0 else -1.0


def params_key(params: dict) -> str:
    return json.dumps(params, sort_keys=True, default=str)


def grid_search(runner: Runner, grid: list[dict] | None = None,
                ledger: str | Path | None = None) -> dict:
    """Run every configuration over the runner's period.

    Returns {"configs": [...], "returns": DataFrame of daily returns (one column per
    configuration), "table": per-configuration statistics, "best": index of the highest
    Sharpe}. Appends each configuration to the trial ledger if a path is given."""
    grid = grid if grid is not None else runner.strategy_cls.grid()
    if not grid:
        raise ValueError("the strategy has no valid parameter combinations")
    columns, rows = {}, []
    for i, params in enumerate(grid):
        result = runner.run(params)
        r = daily_returns(result)
        columns[i] = r
        rows.append({"config": i, **params, "sharpe": sharpe(r), "annual_return": annual_return(r),
                     "max_drawdown": max_drawdown(np.concatenate([[1.0], np.cumprod(1 + r.to_numpy())])),
                     "trades": int(len(result.trades))})
    returns = pd.DataFrame(columns)
    table = pd.DataFrame(rows)
    ranked = table["sharpe"].fillna(-np.inf)
    out = {"configs": grid, "returns": returns, "table": table, "best": int(ranked.idxmax())}
    if ledger is not None:
        record_trials(ledger, grid, table, returns)
    return out


def record_trials(ledger: str | Path, configs: list[dict], table: pd.DataFrame,
                  returns: pd.DataFrame) -> None:
    path = Path(ledger)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with path.open("a") as f:
        for i, params in enumerate(configs):
            f.write(json.dumps({
                "params": params, "recorded": stamp,
                "start": str(returns.index[0].date()), "end": str(returns.index[-1].date()),
                "sharpe": None if not np.isfinite(table.loc[i, "sharpe"]) else float(table.loc[i, "sharpe"]),
            }, default=str) + "\n")


def trial_count(ledger: str | Path) -> int:
    """Number of distinct parameter sets ever recorded for a strategy."""
    path = Path(ledger)
    if not path.exists():
        return 0
    return len({params_key(json.loads(line)["params"]) for line in path.read_text().splitlines() if line.strip()})
