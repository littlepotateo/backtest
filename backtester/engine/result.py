"""RunConfig and RunResult: the only things downstream code depends on.

Every execution backend (the native engine now, LEAN later) turns a strategy and a
RunConfig into a RunResult. Metrics, validation tests, explanations and the dashboard
read RunResult and nothing else.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from backtester.engine.costs import CostModel

FILL_COLUMNS = ["time", "symbol", "qty", "price", "commission", "slippage_cost"]
TRADE_COLUMNS = ["symbol", "side", "qty", "entry_time", "exit_time", "entry_price",
                 "exit_price", "pnl", "return", "costs"]
ORDER_COLUMNS = ["time", "symbol", "qty", "kind"]


@dataclass
class RunConfig:
    start: str | None = None          # first date the strategy may trade
    end: str | None = None
    initial_cash: float = 100_000.0
    costs: CostModel = field(default_factory=CostModel)
    fill: str = "next_open"           # "next_open" (default) or "close" (same-bar, flagged)
    max_leverage: float = 1.0         # gross exposure limit as a multiple of equity
    allow_short: bool = True
    fractional_shares: bool = False
    use_adjusted: bool = True         # scale prices by adj_factor (total-return approximation)
    timezone: str = "America/New_York"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunResult:
    equity: pd.Series                 # account value at each bar close, UTC index
    gross_exposure: pd.Series         # gross position value / equity at each bar close
    fills: pd.DataFrame
    trades: pd.DataFrame              # closed round trips (one row per closing fill)
    orders: pd.DataFrame
    meta: dict

    def save(self, directory: str | Path) -> Path:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"equity": self.equity, "gross_exposure": self.gross_exposure}) \
            .to_parquet(d / "equity.parquet")
        self.fills.to_parquet(d / "fills.parquet")
        self.trades.to_parquet(d / "trades.parquet")
        self.orders.to_parquet(d / "orders.parquet")
        (d / "meta.json").write_text(json.dumps(self.meta, indent=2, default=str))
        return d

    @classmethod
    def load(cls, directory: str | Path) -> "RunResult":
        d = Path(directory)
        eq = pd.read_parquet(d / "equity.parquet")
        return cls(equity=eq["equity"], gross_exposure=eq["gross_exposure"],
                   fills=pd.read_parquet(d / "fills.parquet"),
                   trades=pd.read_parquet(d / "trades.parquet"),
                   orders=pd.read_parquet(d / "orders.parquet"),
                   meta=json.loads((d / "meta.json").read_text()))
