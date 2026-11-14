"""Covered call: hold 100 shares per call sold; each month sell a call about `dte` days
out at about `delta`, and let it expire or be assigned. If the shares are called away
they are bought back at the next open."""

from backtester import Strategy


class CoveredCall(Strategy):
    universe = ["SPY"]
    options_on = ["SPY"]
    interval = "1d"
    params = {"dte": 30, "delta": 0.30}
    param_grid = {"delta": [0.15, 0.30, 0.50], "dte": [30, 45]}

    def on_bar(self, ctx):
        sym = self.universe[0]
        lots = int(ctx.equity / (ctx.price(sym) * 100))
        if ctx.position(sym) < lots * 100 and not ctx.options.positions(sym):
            ctx.order_target(sym, lots * 100)              # (re)build the share position
            return
        if not ctx.options.positions(sym) and ctx.position(sym) >= 100:
            call = ctx.options.select(sym, "C", self.params["dte"], delta=self.params["delta"])
            ctx.options.order(call, -int(ctx.position(sym) // 100))
