"""Option positions inside the native engine.

Orders placed in `on_bar` fill at the next bar's open at the modelled price plus half
the modelled spread, and pay commission per contract. Positions are marked to the model
at every close. Only defined-risk books are accepted (see `_acceptable`).

Expiry (at the close of the expiry date, or the first bar after it):
  - a short call covered by shares is assigned: the shares are sold at the strike;
  - a short put secured by cash is assigned: shares are bought at the strike;
  - everything else settles in cash at intrinsic value (as if closed at the bell).
Early assignment: a short call is assigned the day before the underlying goes
ex-dividend if its remaining time value is less than the dividend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from backtester.options.chain import MULTIPLIER, OptionContract, OptionModel, _day

if TYPE_CHECKING:
    from backtester.engine.native import _Sim


class OptionBook:
    def __init__(self, sim: "_Sim", models: dict[str, OptionModel], per_contract: float = 0.65,
                 min_per_order: float = 1.0):
        self.sim, self.models = sim, models
        self.per_contract, self.min_per_order = per_contract, min_per_order
        self.positions: dict[OptionContract, float] = {}      # contracts (negative = short)
        self.avg_price: dict[OptionContract, float] = {}      # per share
        self.entry_time: dict = {}
        self.entry_costs: dict[OptionContract, float] = {}    # dollars, for the open quantity
        self.pending: dict[OptionContract, float] = {}
        self.marks: dict[OptionContract, float] = {}
        self._entry_fees: dict[OptionContract, float] = {}    # commissions only

    # --- helpers ---------------------------------------------------------------------
    def model(self, contract: OptionContract) -> OptionModel:
        if contract.underlying not in self.models:
            raise KeyError(f"no option model for {contract.underlying}")
        return self.models[contract.underlying]

    def model_for(self, symbol: str) -> OptionModel:
        if symbol not in self.models:
            raise KeyError(f"no option model for {symbol}")
        return self.models[symbol]

    def commission(self, contracts: float) -> float:
        m = self.sim.config.costs.multiplier
        return max(abs(contracts) * self.per_contract, self.min_per_order) * m if contracts else 0.0

    def market_value(self) -> float:
        return sum(q * MULTIPLIER * self.marks.get(c, self.avg_price[c]) for c, q in self.positions.items())

    def mark(self) -> None:
        for c in self.positions:
            spot = self.sim.last_close.get(c.underlying)
            if spot is not None:
                self.marks[c] = self.model(c).value(c, spot, self.sim.now)

    # --- orders ----------------------------------------------------------------------
    def place(self, contract: OptionContract, contracts: float) -> None:
        self.model(contract)
        contracts = float(int(contracts))
        qty = self.pending.get(contract, 0.0) + contracts
        if qty:
            self.pending[contract] = qty
            self.sim.orders.append((self.sim.now, str(contract), qty * MULTIPLIER, "option"))
        else:
            self.pending.pop(contract, None)

    def _acceptable(self, positions: dict, shares: dict, cash: float) -> str | None:
        """None if the book is defined-risk, else the reason it is not.
        Rule 1: beyond the highest strike the account must not lose as the price rises
        (short calls need shares or long calls behind them).
        Rule 2: the account's value at expiry must stay at or above zero at every
        underlying price from 0 to 3x the current price."""
        for sym in {c.underlying for c in positions}:
            legs = [(c, q) for c, q in positions.items() if c.underlying == sym and q]
            if not legs:
                continue
            spot = self.sim.last_close[sym]
            stock = shares.get(sym, 0.0)
            slope = stock + MULTIPLIER * sum(q for c, q in legs if c.right == "C")
            if slope < -1e-9:
                return f"uncovered short call on {sym}"
            grid = np.unique(np.concatenate([[0.0], [c.strike for c, _ in legs], np.linspace(0, 3 * spot, 61)]))
            others = sum(q * self.sim.last_close[s] for s, q in shares.items() if s != sym and q)
            worst = min(cash + others + stock * s + MULTIPLIER * sum(q * c.intrinsic(s) for c, q in legs)
                        for s in grid)
            if worst < -1e-6:
                return f"position on {sym} could lose more than the account holds"
        return None

    def fill_pending(self) -> None:
        sim = self.sim
        ready = [c for c in self.pending if sim.bar_now.get(c.underlying)]
        # closing or reducing orders first, then the legs that add protection (buys)
        ready.sort(key=lambda c: (abs(self.positions.get(c, 0.0) + self.pending[c]) >= abs(self.positions.get(c, 0.0)),
                                  self.pending[c] < 0))
        fills = []
        cash, book = sim.cash, dict(self.positions)
        for c in ready:
            qty = self.pending.pop(c)
            spot = float(sim.arrays[c.underlying]["open"][sim.cursor[c.underlying]])
            model = self.model(c)
            if (c.expiry - _day(sim.now)).days < 0:
                sim.warnings["option_orders_after_expiry"] += 1
                continue
            mid = model.value(c, spot, sim.now, at_open=True)
            half = model.half_spread(mid) * sim.config.costs.multiplier
            px = max(mid + half, 0.01) if qty > 0 else max(mid - half, 0.0)
            fee = self.commission(qty)
            cash -= qty * MULTIPLIER * px + fee
            book[c] = book.get(c, 0.0) + qty
            fills.append((c, qty, px, fee, abs(qty) * MULTIPLIER * abs(px - mid)))
        if not fills:
            return
        reason = self._acceptable(book, sim.positions, cash)
        if reason:
            sim.warnings["option_orders_rejected"] += 1
            sim.records.append({"time": sim.now.isoformat(), "name": "option_order_rejected", "value": reason})
            return
        for c, qty, px, fee, slip in fills:
            self._apply(c, qty, px, fee, slip)

    def _apply(self, c: OptionContract, qty: float, px: float, fee: float, slip: float) -> None:
        sim = self.sim
        pos = self.positions.get(c, 0.0)
        sim.cash -= qty * MULTIPLIER * px + fee
        sim.fills.append((sim.now, str(c), qty * MULTIPLIER, px, fee, slip))
        closing = min(abs(qty), abs(pos)) if pos * qty < 0 else 0.0
        opening = abs(qty) - closing
        per = (fee + slip) / abs(qty)
        if closing:
            self._record_close(c, closing, px, per * closing, fee / abs(qty) * closing)
        if opening:
            held = 0.0 if closing or pos == 0 else abs(pos)
            if held == 0.0:
                self.avg_price[c], self.entry_time[c], self.entry_costs[c] = px, sim.now, 0.0
                self._entry_fees[c] = 0.0
            else:
                self.avg_price[c] = (self.avg_price[c] * held + px * opening) / (held + opening)
            self.entry_costs[c] += per * opening
            self._entry_fees[c] += fee / abs(qty) * opening
        new = pos + qty
        if new:
            self.positions[c] = new
            self.marks[c] = px
        else:
            self._drop(c)

    def _record_close(self, c, contracts, px, exit_costs, exit_fee) -> None:
        sim = self.sim
        pos = self.positions[c]
        direction = 1 if pos > 0 else -1
        share = contracts / abs(pos)
        entry_costs, entry_fee = self.entry_costs[c] * share, self._entry_fees[c] * share
        self.entry_costs[c] -= entry_costs
        self._entry_fees[c] -= entry_fee
        entry = self.avg_price[c]
        pnl = direction * (px - entry) * contracts * MULTIPLIER - exit_fee - entry_fee
        basis = max(entry, 0.01) * contracts * MULTIPLIER
        sim.trades.append((str(c), "long" if direction > 0 else "short", contracts * MULTIPLIER,
                           self.entry_time[c], sim.now, entry, px, pnl, pnl / basis,
                           entry_costs + exit_costs))

    def _drop(self, c) -> None:
        for d in (self.positions, self.avg_price, self.entry_time, self.entry_costs, self.marks,
                  self._entry_fees):
            d.pop(c, None)

    # --- expiry and assignment ----------------------------------------------------------
    def _settle(self, c: OptionContract, spot: float, reason: str) -> None:
        """Remove the position: by assignment into shares where covered, else in cash."""
        sim = self.sim
        qty = self.positions[c]
        value = c.intrinsic(spot)
        itm = value >= 0.01
        shares = sim.positions.get(c.underlying, 0.0)
        hedged = any(o.underlying == c.underlying and o.right == c.right and q > 0 and o.expiry >= c.expiry
                     for o, q in self.positions.items())
        n = abs(qty) * MULTIPLIER
        self._record_close(c, abs(qty), value, 0.0, 0.0)
        sim.cash += qty * MULTIPLIER * value
        covered_call = c.right == "C" and shares >= n
        secured_put = c.right == "P" and sim.cash >= n * spot
        if itm and qty < 0 and not hedged and (covered_call or secured_put):
            # Assignment. Paying intrinsic value and trading the shares at the market
            # price is the same cash as trading them at the strike.
            sim.deliver(c.underlying, -n if c.right == "C" else n, spot)
            sim.records.append({"time": sim.now.isoformat(), "name": f"assigned_{reason}", "value": str(c)})
        self._drop(c)

    def settle_expired(self) -> None:
        today = _day(self.sim.now)
        # shorts first, so a spread's long leg is still there to mark it as hedged
        for c in sorted(self.positions, key=lambda c: self.positions[c] > 0):
            if c.expiry <= today and self.sim.bar_now.get(c.underlying):
                self._settle(c, self.sim.last_close[c.underlying], "at_expiry")

    def early_assignment(self, next_dividend: dict[str, float]) -> None:
        for c in list(self.positions):
            d = next_dividend.get(c.underlying, 0.0)
            if d <= 0 or c.right != "C" or self.positions[c] >= 0:
                continue
            spot = self.sim.last_close[c.underlying]
            time_value = self.marks.get(c, 0.0) - c.intrinsic(spot)
            if c.intrinsic(spot) > 0 and time_value < d:
                self._settle(c, spot, "early_before_dividend")
