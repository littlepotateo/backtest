"""The strategy interface.

A strategy sees the market only through `Context`, which exposes bars up to and
including the one that just closed. Orders placed in `on_bar` fill on the next bar.

The shape mirrors QuantConnect LEAN (`initialize` / `on_data`, `set_holdings`) so a
strategy can be translated mechanically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from backtester.engine.native import _Sim


class Strategy:
    name: str = ""
    universe: list[str] = []
    interval: str = "1d"
    params: dict = {}          # default parameters; override per run
    param_grid: dict = {}      # values to try per parameter, e.g. {"fast": [20, 50]}
    warmup_bars: int = 0       # bars of history wanted before the first tradable bar

    @classmethod
    def valid_params(cls, params: dict) -> bool:
        """Override to exclude meaningless combinations (e.g. fast >= slow)."""
        return True

    @classmethod
    def grid(cls) -> list[dict]:
        """Every valid parameter combination from `param_grid` (defaults for the rest)."""
        import itertools
        keys = list(cls.param_grid)
        combos = [dict(zip(keys, v)) for v in itertools.product(*(cls.param_grid[k] for k in keys))]
        out = [{**cls.params, **c} for c in combos] or [dict(cls.params)]
        return [p for p in out if cls.valid_params(p)]

    def __init__(self, **params):
        unknown = set(params) - set(type(self).params)
        if unknown:
            raise ValueError(f"unknown parameters for {type(self).__name__}: {sorted(unknown)}")
        self.params = {**type(self).params, **params}
        if not self.name:
            self.name = type(self).__name__

    def init(self, ctx: "Context") -> None:
        """Called once before the first bar."""

    def on_bar(self, ctx: "Context") -> None:
        """Called after each bar closes."""
        raise NotImplementedError


class Context:
    """What a strategy can see and do at the current bar."""

    def __init__(self, sim: "_Sim"):
        self._sim = sim

    # --- time -------------------------------------------------------------------
    @property
    def now(self) -> pd.Timestamp:
        """Start time (UTC) of the bar that just closed."""
        return self._sim.now

    @property
    def params(self) -> dict:
        return self._sim.strategy.params

    # --- market data (never beyond the current bar) -------------------------------
    def has_bar(self, symbol: str) -> bool:
        """True if `symbol` has a bar at the current time."""
        return self._sim.bar_now.get(symbol, False)

    def history(self, symbol: str, n: int | None = None) -> pd.DataFrame:
        """Bars for `symbol` up to and including the current one (the last `n` if given)."""
        j = self._sim.cursor.get(symbol, -1)
        df = self._sim.data[symbol]
        lo = 0 if n is None else max(0, j + 1 - n)
        return df.iloc[lo:j + 1]

    def closes(self, symbol: str, n: int | None = None) -> np.ndarray:
        """Closing prices up to and including the current bar, as an array."""
        j = self._sim.cursor.get(symbol, -1)
        arr = self._sim.arrays[symbol]["close"]
        lo = 0 if n is None else max(0, j + 1 - n)
        return arr[lo:j + 1]

    def returns(self, symbols: list[str] | None = None, n: int | None = None) -> pd.DataFrame:
        """Per-bar returns of several symbols, aligned by time, up to and including the
        current bar (the last `n` rows if given). Rows where any symbol has no bar are
        dropped."""
        symbols = list(symbols or self._sim.data)
        closes = pd.DataFrame({s: self.history(s)["close"] for s in symbols}).dropna()
        out = closes.pct_change().iloc[1:]
        return out if n is None else out.iloc[-n:]

    def price(self, symbol: str) -> float:
        """Latest known close for `symbol` (NaN if it has not traded yet)."""
        return self._sim.last_close.get(symbol, float("nan"))

    # --- session helpers (intraday) -------------------------------------------------
    def session_date(self, symbol: str):
        return self._sim.session_info(symbol, "date")

    def bars_into_session(self, symbol: str) -> int:
        """0 for the first bar of the trading day, 1 for the second, ..."""
        return int(self._sim.session_info(symbol, "into"))

    def bars_left_in_session(self, symbol: str) -> int:
        """Bars remaining today after the current one. An order placed when this is 1
        fills at the open of the day's last bar."""
        return int(self._sim.session_info(symbol, "left"))

    # --- account ------------------------------------------------------------------
    @property
    def cash(self) -> float:
        return self._sim.cash

    @property
    def equity(self) -> float:
        return self._sim.equity()

    def position(self, symbol: str) -> float:
        """Shares held (negative when short)."""
        return self._sim.positions.get(symbol, 0.0)

    # --- orders (fill on the next bar) ----------------------------------------------
    def order(self, symbol: str, qty: float) -> None:
        """Buy (`qty` > 0) or sell (`qty` < 0) shares at the next bar."""
        self._sim.place(symbol, qty, "market", replace=False)

    def order_target(self, symbol: str, qty: float) -> None:
        """Trade so that the position becomes `qty` shares."""
        self._sim.place(symbol, qty - self.position(symbol), "target", replace=True)

    def rebalance(self, weights: dict) -> None:
        """Trade toward target weights ({symbol: fraction of equity}). Symbols in the
        universe that are not mentioned are sold. Sales fill before purchases."""
        for symbol in self._sim.data:
            self.order_target_percent(symbol, float(weights.get(symbol, 0.0)))

    def record(self, name: str, value) -> None:
        """Save something for the run report (e.g. the weights chosen at a rebalance)."""
        self._sim.records.append({"time": self.now.isoformat(), "name": name, "value": value})

    def order_target_percent(self, symbol: str, pct: float) -> None:
        """Trade so that the position is `pct` of account equity (1.0 = fully invested,
        negative = short), sized at the latest close."""
        px = self.price(symbol)
        if not np.isfinite(px):
            return
        self.order_target(symbol, pct * self.equity / px)
