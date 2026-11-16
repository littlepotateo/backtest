"""Moving-average timing of asset classes, after Faber (2007), "A Quantitative Approach
to Tactical Asset Allocation" (The Journal of Wealth Management).

Each month-end, hold an asset (equal share of the portfolio) if its price is above the
average of its last `months` month-end prices; otherwise hold cash. The paper's asset
classes are US stocks, developed-market stocks, 10-year Treasuries, commodities and
real estate; the default universe uses ETFs as stand-ins (an assumption).
`timing = False` holds every asset all the time, for comparison.

ASSUMPTION: the paper's full text was not read (only its abstract, which says "a
moving-average timing model"). The 10-month average, month-end signal and equal weights
here come from recollection of the method, not from a source checked in this project.
"""

from backtester import Strategy


class FaberTiming(Strategy):
    universe = ["SPY", "EFA", "IEF", "DBC", "VNQ"]
    interval = "1d"
    params = {"months": 10, "timing": True}
    param_grid = {"months": [8, 10, 12]}

    def init(self, ctx):
        self.month = None

    def month_ends(self, ctx, symbol, count):
        """Closes at the last bar of each completed month, oldest first, as of the latest bar."""
        h = ctx.history(symbol)["close"]
        local = h.index.tz_convert("America/New_York")
        key = local.year * 100 + local.month
        last = h.groupby(key).last()
        return last.iloc[:-1].to_numpy()[-count:]          # drop the month in progress

    def on_bar(self, ctx):
        day = ctx.now.tz_convert("America/New_York")
        month = (day.year, day.month)
        if month == self.month:
            return
        self.month = month
        n = self.params["months"]
        weights = {}
        for s in self.universe:
            ends = self.month_ends(ctx, s, n)
            if len(ends) < n:
                continue
            if not self.params["timing"] or ends[-1] > ends.mean():
                weights[s] = 1 / len(self.universe)
        if weights or self.params["timing"] is False:
            ctx.rebalance(weights)
        elif any(ctx.position(s) for s in self.universe):
            ctx.rebalance({})
