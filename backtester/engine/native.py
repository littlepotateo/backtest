"""The native bar-by-bar engine.

Per bar, in order:
  1. orders placed on the previous bar fill at this bar's open (plus slippage, commission);
  2. the account is marked at this bar's close;
  3. the strategy's `on_bar` runs, seeing bars up to and including this one, and may
     place orders for the next bar.
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np
import pandas as pd

from backtester.data.cache import to_utc
from backtester.engine.result import (FILL_COLUMNS, ORDER_COLUMNS, TRADE_COLUMNS,
                                      RunConfig, RunResult)
from backtester.engine.strategy import Context, Strategy


class _Sim:
    """Mutable state of one run. Strategies reach it only through Context."""

    def __init__(self, strategy: Strategy, data: dict[str, pd.DataFrame], config: RunConfig):
        self.strategy, self.data, self.config = strategy, data, config
        self.arrays = {s: {c: df[c].to_numpy() for c in ("open", "high", "low", "close")}
                       for s, df in data.items()}
        self.cursor: dict[str, int] = {}
        self.bar_now: dict[str, bool] = {}
        self.last_close: dict[str, float] = {}
        self.now: pd.Timestamp | None = None
        self.cash = float(config.initial_cash)
        self.positions: dict[str, float] = {}
        self.avg_price: dict[str, float] = {}
        self.entry_time: dict[str, pd.Timestamp] = {}
        self.entry_cost_per_share: dict[str, float] = {}   # commission + slippage
        self.entry_fee_per_share: dict[str, float] = {}    # commission only
        self.pending: dict[str, float] = {}
        self.orders: list[tuple] = []
        self.fills: list[tuple] = []
        self.trades: list[tuple] = []
        self.warnings: Counter = Counter()
        self._sessions = {}
        for s, df in data.items():
            local = df.index.tz_convert(config.timezone)
            dates = pd.Series(local.date, index=df.index)
            grp = dates.groupby(dates)
            self._sessions[s] = {"date": dates.to_numpy(),
                                 "into": grp.cumcount().to_numpy(),
                                 "left": grp.cumcount(ascending=False).to_numpy()}

    # --- views -------------------------------------------------------------------
    def session_info(self, symbol: str, key: str):
        j = self.cursor.get(symbol, -1)
        if j < 0:
            raise ValueError(f"{symbol} has no bars yet")
        return self._sessions[symbol][key][j]

    def gross(self) -> float:
        return sum(abs(q) * self.last_close[s] for s, q in self.positions.items() if q)

    def equity(self) -> float:
        return self.cash + sum(q * self.last_close[s] for s, q in self.positions.items() if q)

    # --- orders ------------------------------------------------------------------
    def place(self, symbol: str, qty: float, kind: str, replace: bool) -> None:
        if symbol not in self.data:
            raise KeyError(f"{symbol} is not in the strategy's universe")
        if not math.isfinite(qty):
            raise ValueError(f"order quantity for {symbol} is not a number")
        if not self.config.fractional_shares:
            qty = float(math.trunc(qty))
        qty = qty if replace else self.pending.get(symbol, 0.0) + qty
        if qty == 0:
            self.pending.pop(symbol, None)
            return
        self.pending[symbol] = qty
        self.orders.append((self.now, symbol, qty, kind))

    def fill_pending(self, price_field: str) -> None:
        for symbol in [s for s in self.pending if self.bar_now.get(s)]:
            qty = self.pending.pop(symbol)
            raw = float(self.arrays[symbol][price_field][self.cursor[symbol]])
            self._fill(symbol, qty, raw)

    def _fill(self, symbol: str, qty: float, raw_price: float) -> None:
        cfg, costs = self.config, self.config.costs
        pos = self.positions.get(symbol, 0.0)
        target = pos + qty
        if not cfg.allow_short and target < 0:
            target = 0.0
            self.warnings["short_orders_blocked"] += 1
        side = 1 if target > pos else -1
        price = costs.fill_price(raw_price, side)
        if abs(target) > abs(pos) or target * pos < 0:
            # the order adds exposure: keep gross exposure within the leverage limit
            others = self.gross() - abs(pos) * self.last_close.get(symbol, raw_price)
            equity = self.equity()
            est_fee = costs.commission(abs(target - pos), price)
            room = (cfg.max_leverage * (equity - est_fee) - others) / price
            limit = max(room, 0.0)
            if not cfg.fractional_shares:
                limit = float(math.floor(limit + 1e-9))
            if abs(target) > limit:
                # never force a position to grow; only stop it growing further
                capped = math.copysign(limit, target)
                target = capped if target * pos < 0 or abs(capped) >= abs(pos) else pos
                self.warnings["orders_reduced_for_buying_power"] += 1
        qty = target - pos
        if qty == 0:
            return
        fee = costs.commission(abs(qty), price)
        slip = abs(qty) * abs(price - raw_price)
        self.cash -= qty * price + fee
        self.fills.append((self.now, symbol, qty, price, fee, slip))

        closing = min(abs(qty), abs(pos)) if pos * qty < 0 else 0.0
        opening = abs(qty) - closing
        fee_per_share = fee / abs(qty)
        slip_per_share = slip / abs(qty)
        if closing:
            direction = 1 if pos > 0 else -1
            entry = self.avg_price[symbol]
            entry_costs = self.entry_cost_per_share[symbol] * closing
            exit_costs = (fee_per_share + slip_per_share) * closing
            # prices already include slippage, so only commissions come off here
            pnl = direction * (price - entry) * closing \
                - fee_per_share * closing - self.entry_fee_per_share[symbol] * closing
            self.trades.append((symbol, "long" if direction > 0 else "short", closing,
                                self.entry_time[symbol], self.now, entry, price, pnl,
                                pnl / (entry * closing), entry_costs + exit_costs))
        new_pos = pos + qty
        if opening:
            if closing or pos == 0:      # fresh position (possibly after a reversal)
                self.avg_price[symbol] = price
                self.entry_time[symbol] = self.now
                self.entry_cost_per_share[symbol] = fee_per_share + slip_per_share
                self.entry_fee_per_share[symbol] = fee_per_share
            else:                         # adding to an existing position
                held = abs(pos)
                total = held + opening
                self.avg_price[symbol] = (self.avg_price[symbol] * held + price * opening) / total
                self.entry_cost_per_share[symbol] = (
                    self.entry_cost_per_share[symbol] * held
                    + (fee_per_share + slip_per_share) * opening) / total
                self.entry_fee_per_share[symbol] = (
                    self.entry_fee_per_share[symbol] * held + fee_per_share * opening) / total
        self.positions[symbol] = new_pos
        self.last_close.setdefault(symbol, raw_price)


class NativeBackend:
    name = "native"

    def run(self, strategy: Strategy, data: dict[str, pd.DataFrame], config: RunConfig,
            data_meta: dict | None = None) -> RunResult:
        if config.fill not in ("next_open", "close"):
            raise ValueError("fill must be 'next_open' or 'close'")
        missing = [s for s in strategy.universe if s not in data]
        if missing:
            raise ValueError(f"no data for: {missing}")
        data = {s: self._prepare(data[s], config) for s in strategy.universe}
        end = to_utc(config.end).normalize() + pd.Timedelta(days=1) if config.end else None
        if end is not None:
            data = {s: df[df.index < end] for s, df in data.items()}
        timeline = sorted(set().union(*[df.index for df in data.values()]))
        if not timeline:
            raise ValueError("no bars in the requested period")
        timeline = pd.DatetimeIndex(timeline)
        trade_start = to_utc(config.start) if config.start else timeline[0]
        index_of = {s: df.index.get_indexer(timeline) for s, df in data.items()}

        sim = _Sim(strategy, data, config)
        ctx = Context(sim)
        started = False
        times, equity, exposure = [], [], []
        for k, t in enumerate(timeline):
            sim.now = t
            for s in data:
                j = index_of[s][k]
                sim.bar_now[s] = j >= 0
                if j >= 0:
                    sim.cursor[s] = j
            if t < trade_start:
                for s in data:
                    if sim.bar_now[s]:
                        sim.last_close[s] = float(sim.arrays[s]["close"][sim.cursor[s]])
                continue
            if not started:
                strategy.init(ctx)
                started = True
            if config.fill == "next_open":
                sim.fill_pending("open")
            for s in data:
                if sim.bar_now[s]:
                    sim.last_close[s] = float(sim.arrays[s]["close"][sim.cursor[s]])
            strategy.on_bar(ctx)
            if config.fill == "close":
                sim.fill_pending("close")
            eq = sim.equity()
            times.append(t)
            equity.append(eq)
            exposure.append(sim.gross() / eq if eq > 0 else 0.0)
        if not times:
            raise ValueError("the start date is after the last available bar")

        idx = pd.DatetimeIndex(times, name="time")
        meta = {
            "backend": self.name,
            "strategy": strategy.name,
            "params": strategy.params,
            "universe": list(strategy.universe),
            "interval": strategy.interval,
            "config": config.to_dict(),
            "period": {"start": idx[0].isoformat(), "end": idx[-1].isoformat(), "bars": len(idx)},
            "data": data_meta or {},
            "open_positions": {s: q for s, q in sim.positions.items() if q},
            "unfilled_orders": dict(sim.pending),
            "warnings": dict(sim.warnings),
            "notes": self._notes(config),
        }
        return RunResult(
            equity=pd.Series(equity, index=idx, name="equity"),
            gross_exposure=pd.Series(exposure, index=idx, name="gross_exposure"),
            fills=pd.DataFrame(sim.fills, columns=FILL_COLUMNS),
            trades=pd.DataFrame(sim.trades, columns=TRADE_COLUMNS),
            orders=pd.DataFrame(sim.orders, columns=ORDER_COLUMNS),
            meta=meta)

    @staticmethod
    def _prepare(df: pd.DataFrame, config: RunConfig) -> pd.DataFrame:
        if config.use_adjusted and "adj_factor" in df.columns:
            df = df.copy()
            for c in ("open", "high", "low", "close"):
                df[c] = df[c] * df["adj_factor"]
        return df

    @staticmethod
    def _notes(config: RunConfig) -> list[str]:
        notes = []
        if config.fill == "close":
            notes.append("Orders fill at the close of the bar that generated them. "
                         "This is optimistic; next-bar-open fills are the default.")
        if not config.costs.confirmed:
            notes.append("Commission rates are unconfirmed placeholders (config/costs.toml).")
        notes.append("Short borrow fees and margin interest are not modelled.")
        return notes
