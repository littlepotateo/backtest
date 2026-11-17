"""Trading costs applied at fill time."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from backtester import paths


@dataclass(frozen=True)
class CostModel:
    per_share: float = 0.005
    min_per_order: float = 1.0
    max_pct_of_trade: float = 0.01
    slippage_bps: float = 1.0
    multiplier: float = 1.0   # scales commission and slippage together (cost stress)
    confirmed: bool = False   # False until the rates are checked against the broker

    def commission(self, shares: float, price: float) -> float:
        """Commission in dollars for one order of `shares` at `price`."""
        shares = abs(shares)
        if shares == 0 or self.multiplier == 0:
            return 0.0
        value = shares * price
        fee = max(shares * self.per_share, self.min_per_order)
        if self.max_pct_of_trade > 0:
            fee = min(fee, value * self.max_pct_of_trade)
        return fee * self.multiplier

    def fill_price(self, price: float, side: int) -> float:
        """Price paid (side=+1 buy) or received (side=-1 sell) after slippage."""
        return price * (1 + side * self.slippage_bps / 1e4 * self.multiplier)

    def scaled(self, multiplier: float) -> "CostModel":
        return CostModel(**{**asdict(self), "multiplier": multiplier})

    @classmethod
    def zero(cls) -> "CostModel":
        return cls(per_share=0, min_per_order=0, max_pct_of_trade=0, slippage_bps=0, confirmed=True)

    @classmethod
    def from_toml(cls, path: str | Path | None = None) -> "CostModel":
        path = Path(path or paths.COSTS)
        if not path.exists():
            return cls()
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        return cls(confirmed=bool(raw.get("confirmed", False)), **raw.get("stock", {}))
