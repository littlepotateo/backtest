"""Market intraday momentum on SPY (Gao, Han, Li and Zhou, 2017) for the backtest engine.

Each day the first half-hour return r1 (previous close to 10:00) and the twelfth half-hour return r12 (15:00 to 15:30) decide the position
held for the last half-hour (15:30 to 16:00), which is closed at the close:

    mode "timing": long if the signal is positive, short otherwise (signal "r1", eq. 4), or long only if r1 and r12 are both positive, short
                   if both are not, flat otherwise (signal "r1_r12", eq. 5); the whole account is used.
    mode "mean_variance": weight = rhat / (gamma sigma2), limited to [-0.5, 1.5] (eq. 6), where rhat comes from a regression of the last
                   half-hour return on r1 (and r12) re-estimated each month on all earlier days (the paper's recursive scheme).

RUN IT WITH `--fill close --no-cash-interest` (and `--max-leverage 1.5` for mode mean_variance, which may borrow 50%): orders then fill at the close of the bar on which they are placed. The entry order is placed
on the close of the 15:00-15:30 bar and fills at that 15:30 price; the exit order is placed on the last bar and fills at the 16:00 close, as in
the paper. Decisions use only data up to the bar's close (`bt check` verifies this). Costs come from config/costs.toml (IBKR).

ASSUMPTIONS the paper does not settle (spec.md): the regression variance forecast is the training residual variance; the regression is
refit monthly; days with fewer than 13 half-hour bars (half-days, missing bars) are skipped; the first `min_obs` days only collect data.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from backtester import Strategy

HERE = Path(__file__).parent


def _sibling(name: str):
    spec = importlib.util.spec_from_file_location(f"intraday_momentum_{name}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


signals, sizing, predict = _sibling("signals"), _sibling("sizing"), _sibling("predict")


class IntradayMomentum(Strategy):
    universe = ["SPY"]
    interval = "30m"
    params = {"signal": "r1", "mode": "timing", "gamma": 5.0, "min_obs": 60}
    param_grid = {"signal": ["r1", "r1_r12"], "mode": ["timing", "mean_variance"]}

    @classmethod
    def valid_params(cls, p):
        return p["signal"] in ("r1", "r1_r12") and p["mode"] in ("timing", "mean_variance") and p["gamma"] > 0

    def init(self, ctx):
        self.prev_close = None
        self.day = None
        self.p = {}
        self.history = []          # completed days: (month key, r1, r12, r13)
        self.fit_key = None
        self.fit = None

    # -- helpers -------------------------------------------------------------------------------------------------------
    def _cols(self):
        return (1,) if self.params["signal"] == "r1" else (1, 2)

    def _refit(self, month):
        rows = [h for h in self.history if h[0] < month]
        if len(rows) < self.params["min_obs"]:
            self.fit = None
        else:
            cols = self._cols()
            X = np.array([[h[c] for c in cols] for h in rows])
            y = np.array([h[3] for h in rows])
            Z = np.column_stack([np.ones(len(rows)), X])
            beta = np.linalg.lstsq(Z, y, rcond=None)[0]
            e = y - Z @ beta
            self.fit = (beta, float(e @ e / (len(rows) - Z.shape[1])))
        self.fit_key = month

    # -- the strategy --------------------------------------------------------------------------------------------------
    def on_bar(self, ctx):
        s = self.universe[0]
        if not ctx.has_bar(s):
            return
        day, into, left = ctx.session_date(s), ctx.bars_into_session(s), ctx.bars_left_in_session(s)
        if day != self.day:
            self.day, self.p = day, {}
        price = ctx.price(s)
        self.p[into] = price
        if into == 0 and self.prev_close:
            self.p["r1"] = price / self.prev_close - 1                      # previous close to the 10:00 price
        complete = into == 11 and all(k in self.p for k in range(12))
        if complete and "r1" in self.p:
            r1, r12 = self.p["r1"], price / self.p[10] - 1                    # the 12th half-hour: 15:00 -> 15:30
            self.p["r12"] = r12
            if self.params["mode"] == "timing":
                one_signal = self.params["signal"] == "r1"
                sig = int(signals.timing_signal(pd.Series([r1]), None if one_signal else pd.Series([r12])).iloc[0])
                ctx.order_target_percent(s, float(sig))
            else:
                month = (day.year, day.month)
                if month != self.fit_key:
                    self._refit(month)
                if self.fit is not None:
                    beta, sigma2 = self.fit
                    x = [r1] if self.params["signal"] == "r1" else [r1, r12]
                    rhat = beta[0] + float(np.dot(beta[1:], x))
                    w = float(np.clip(rhat / (self.params["gamma"] * sigma2), -0.5, 1.5))
                    ctx.order_target_percent(s, w)
        if left == 0:
            if ctx.position(s):
                ctx.order_target(s, 0)                                       # closed at the 16:00 close
            if "r1" in self.p and "r12" in self.p and 12 in self.p:
                self.history.append(((day.year, day.month), self.p["r1"], self.p["r12"], price / self.p[11] - 1))
            self.prev_close = price
