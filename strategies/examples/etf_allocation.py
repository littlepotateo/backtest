"""Monthly-rebalanced ETF portfolio with a choice of weighting method.

Methods: equal, inverse_vol, risk_parity, min_variance, black_litterman.

For Black-Litterman the reference portfolio is `reference` (default 60% SPY / 40% AGG
style weights given below) and the views come from a momentum rule: the assets with the
best return over the past year (skipping the latest month) are expected to beat the
worst by `view_spread` a year, held with `view_confidence`.
"""

from backtester import Strategy
from backtester.portfolio import View, allocate


class EtfAllocation(Strategy):
    universe = ["SPY", "EFA", "EEM", "AGG", "GLD", "VNQ"]
    interval = "1d"
    params = {"method": "black_litterman", "lookback": 252, "max_weight": 0.4,
              "top": 2, "view_spread": 0.04, "view_confidence": 0.3}
    param_grid = {"method": ["equal", "inverse_vol", "risk_parity", "min_variance", "black_litterman"]}
    # ASSUMPTION: a rough global multi-asset reference portfolio, not measured market values.
    reference = {"SPY": 0.35, "EFA": 0.15, "EEM": 0.05, "AGG": 0.35, "GLD": 0.05, "VNQ": 0.05}

    def init(self, ctx):
        self.month = None

    def momentum_views(self, ctx, symbols):
        scores = {}
        for s in symbols:
            c = ctx.closes(s, 253)
            if len(c) >= 253:
                scores[s] = c[-22] / c[0] - 1          # past year, skipping the latest month
        k = self.params["top"]
        if len(scores) < 2 * k:
            return []
        ranked = sorted(scores, key=scores.get)
        losers, winners = ranked[:k], ranked[-k:]
        weights = {**{s: 1 / k for s in winners}, **{s: -1 / k for s in losers}}
        return [View(weights, self.params["view_spread"], self.params["view_confidence"])]

    def on_bar(self, ctx):
        day = ctx.now.tz_convert("America/New_York")
        month = (day.year, day.month)
        if month == self.month:
            return
        self.month = month
        symbols = [s for s in self.universe if len(ctx.closes(s, 60)) >= 60]
        if len(symbols) < 2:
            return
        method = self.params["method"]
        kwargs = {"max_weight": self.params["max_weight"]}
        if method == "black_litterman":
            total = sum(self.reference[s] for s in symbols)
            kwargs["prior_weights"] = {s: self.reference[s] / total for s in symbols}
            kwargs["views"] = self.momentum_views(ctx, symbols)
        result = allocate(method, ctx.returns(symbols, self.params["lookback"]), **kwargs)
        ctx.rebalance(result["weights"])
        ctx.record("rebalance", result)
