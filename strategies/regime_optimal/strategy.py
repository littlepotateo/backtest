"""Sharpe-optimal regime-dependent allocation, after Zakamulin (2026), "Rethinking Trend Following: Optimal Regime-Dependent
Allocation" (working paper, University of Agder, 9 March 2026).

Each month the market is in a regime observed at the end of the previous month. Two regimes (Bull / Bear): the sign of the trailing
12-month excess return. Four regimes (Bull / Correction / Bear / Rebound): that sign (slow signal) together with the sign of the
latest month's excess return (fast signal). The fraction of wealth held in the risky asset in each regime is chosen ONCE, on a
training window, by the paper's closed form (its equations 16-19), and held fixed afterwards:

    score_s = mean(r | regime s) / mean(r^2 | regime s)        # m_s / q_s
    w_s     = max(score_s / max_j score_j, -1)                 # the best regime gets 1; the floor is a full short

`mode = "tsm"` is the canonical time-series momentum rule (+1 in Bull, -1 in Bear) and `mode = "dsm"` the dynamic-speed momentum
rule of Goulding, Harvey and Mazzoleni (2023) (Bull +1, Bear -1, Correction and Rebound weights chosen to maximise the training
Sharpe ratio), the paper's two benchmarks. The risky asset is an index of the US market EXCESS return (see make_data.py), so the
rest of wealth in cash earns nothing and the engine's Sharpe ratio is the paper's.

ASSUMPTIONS (the paper does not settle these; spec.md has the reasoning):
- the trailing 12-month return is the SUM of the 12 monthly excess returns (compounding gives different numbers; the sum reproduces
  the paper's reported TSM Sharpe ratios);
- the weight is set at the close of the last business day of each month (the paper sets it at the month end) and filled at the next
  open, which in this data equals that close. The calendar is weekdays only, so if a month's last weekday is a market holiday the
  update happens on the first bar of the next month instead (one trading day late, in a handful of months);
- a regime with no positive score for any regime (no regime has a positive signal-to-noise ratio) means no investment;
- the training window ends at `train_end` and weights are estimated only from months up to it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtester import Strategy

BULL, CORRECTION, BEAR, REBOUND = 1, 2, 3, 4


def regime_codes(r: pd.Series, four: bool) -> pd.Series:
    """Regime observed at the end of each month. Two regimes: 1 = Bull, 0 = Bear. Four: see the constants above.
    `r` is the monthly excess return series; the slow signal is the sum of the last 12 months."""
    slow_up = r.rolling(12).sum() > 0
    if not four:
        code = pd.Series(np.where(slow_up, 1, 0), index=r.index, dtype=float)
    else:
        fast_up = r > 0
        code = pd.Series(np.select([slow_up & fast_up, slow_up & ~fast_up, ~slow_up & ~fast_up, ~slow_up & fast_up],
                                   [BULL, CORRECTION, BEAR, REBOUND], default=0), index=r.index, dtype=float)
    code[r.rolling(12).sum().isna()] = np.nan
    return code


def optimal_weights(r: pd.Series, s: pd.Series, states: list[int]) -> dict[int, float]:
    """The paper's equations (16)-(19). `r` is the return of the month and `s` the regime observed at the end of the month before."""
    score = {}
    for k in states:
        x = r[s == k]
        score[k] = float(x.mean() / (x ** 2).mean()) if len(x) else 0.0
    c = max(score.values())
    if c <= 0:
        return {k: 0.0 for k in states}
    return {k: max(v / c, -1.0) for k, v in score.items()}


def dsm_weights(r: pd.Series, s: pd.Series) -> dict[int, float]:
    """Bull +1, Bear -1; Correction and Rebound weights in [-1, 1] that maximise the training Sharpe ratio."""
    from scipy.optimize import minimize

    def neg_sharpe(x):
        R = r * s.map({BULL: 1.0, CORRECTION: x[0], BEAR: -1.0, REBOUND: x[1]})
        return -R.mean() / R.std(ddof=1)
    best = min((minimize(neg_sharpe, st, bounds=[(-1, 1), (-1, 1)], method="L-BFGS-B") for st in ([0, 0], [.5, -.5], [-.5, .5], [1, -1])),
               key=lambda res: res.fun)
    return {BULL: 1.0, CORRECTION: float(best.x[0]), BEAR: -1.0, REBOUND: float(best.x[1])}


class RegimeOptimal(Strategy):
    universe = ["FFMKT"]
    interval = "1d"
    params = {"mode": "opt", "states": 2, "train_end": "1968-12-31"}
    param_grid = {"states": [2, 4]}

    @classmethod
    def valid_params(cls, p):
        return p["mode"] in ("opt", "tsm", "dsm") and p["states"] in (2, 4) and not (p["mode"] == "tsm" and p["states"] != 2) \
            and not (p["mode"] == "dsm" and p["states"] != 4)

    def init(self, ctx):
        self.done = None            # (year, month) of the last month whose regime was acted on
        self.seen = None
        self.fit_key = None
        self.weights = None
        self.fitted_on = None

    def monthly_returns(self, ctx, include_current: bool) -> pd.Series:
        """Excess returns of completed months, oldest first. With include_current the latest bar is the month's last bar."""
        close = ctx.history(self.universe[0])["close"]
        local = close.index.tz_convert("America/New_York")
        ends = close.groupby([local.year, local.month]).last()
        r = ends.pct_change().dropna()
        r.index = pd.PeriodIndex([pd.Period(year=y, month=m, freq="M") for y, m in r.index], freq="M")
        return r if include_current else r.iloc[:-1]

    def fit(self, r: pd.Series) -> dict[int, float]:
        p, four = self.params, self.params["states"] == 4
        s = regime_codes(r, four).shift(1)
        train_end = pd.Period(p["train_end"], "M")
        d = pd.DataFrame({"r": r, "s": s}).dropna()
        d = d[d.index <= train_end]
        self.fitted_on = (str(d.index[0]), str(d.index[-1]), len(d))
        if p["mode"] == "tsm":
            return {1: 1.0, 0: -1.0}
        if p["mode"] == "dsm":
            return dsm_weights(d.r, d.s)
        return optimal_weights(d.r, d.s, [BULL, CORRECTION, BEAR, REBOUND] if four else [0, 1])

    def on_bar(self, ctx):
        day = ctx.now.tz_convert("America/New_York")
        if day.date() < pd.Timestamp(self.params["train_end"]).date():
            return                                                               # inside the training window: nothing to act on yet
        month = (day.year, day.month)
        previous = (day.year, day.month - 1) if day.month > 1 else (day.year - 1, 12)
        first_bar_of_month = month != self.seen
        self.seen = month
        if (day + pd.offsets.BDay(1)).month != day.month and self.done != month:
            include_current, covers = True, month                                # the last business day: act on this month's regime
        elif first_bar_of_month and self.done != previous:
            include_current, covers = False, previous                            # catch-up: last month's final bar was a holiday
        else:
            return
        r = self.monthly_returns(ctx, include_current)
        self.done = covers
        key = (self.params["mode"], self.params["states"], self.params["train_end"])
        if self.weights is None or self.fit_key != key:                          # walk-forward switches parameters mid-run: refit
            self.weights, self.fit_key = self.fit(r), key
        code = regime_codes(r, self.params["states"] == 4)
        if code.empty or np.isnan(code.iloc[-1]):
            return
        w = self.weights[int(code.iloc[-1])]
        ctx.record("regime", float(code.iloc[-1]))
        ctx.record("weight", float(w))
        ctx.order_target_percent(self.universe[0], float(w))
