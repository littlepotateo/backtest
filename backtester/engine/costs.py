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
    sell_value_fee: float = 0.0       # fraction of the value sold (the SEC transaction fee)
    sell_share_fee: float = 0.0       # USD per share sold (the FINRA trading activity fee)
    sell_share_fee_cap: float = 0.0   # most the per-share sell fee can reach on one trade (0 = no cap)
    share_fee: float = 0.0            # USD per share on every fill (audit-trail and clearing fees)
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

    def regulatory_fee(self, qty: float, price: float) -> float:
        """Regulatory and clearing fees of one fill, in dollars. `qty` is signed: negative is a sale, which also pays the SEC and
        FINRA fees. Commission is separate (see `commission`)."""
        shares = abs(qty)
        if shares == 0 or self.multiplier == 0:
            return 0.0
        fee = shares * self.share_fee
        if qty < 0:
            fee += shares * price * self.sell_value_fee
            taf = shares * self.sell_share_fee
            fee += min(taf, self.sell_share_fee_cap) if self.sell_share_fee_cap > 0 else taf
        return fee * self.multiplier

    def fill_price(self, price: float, side: int) -> float:
        """Price paid (side=+1 buy) or received (side=-1 sell) after slippage."""
        return price * (1 + side * self.slippage_bps / 1e4 * self.multiplier)

    def scaled(self, multiplier: float) -> "CostModel":
        return CostModel(**{**asdict(self), "multiplier": multiplier})

    @classmethod
    def zero(cls) -> "CostModel":
        return cls(per_share=0, min_per_order=0, max_pct_of_trade=0, slippage_bps=0, confirmed=True,
                   sell_value_fee=0, sell_share_fee=0, sell_share_fee_cap=0, share_fee=0)

    @classmethod
    def from_toml(cls, path: str | Path | None = None) -> "CostModel":
        path = Path(path or paths.COSTS)
        if not path.exists():
            return cls()
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        return cls(confirmed=bool(raw.get("confirmed", False)), **raw.get("stock", {}))
