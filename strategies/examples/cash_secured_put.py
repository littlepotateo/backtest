"""Cash-secured put: each month sell puts about `dte` days out at about `delta`, backed
by enough cash to buy the shares. If assigned, sell the shares at the next open and
start again."""

from backtester import Strategy


class CashSecuredPut(Strategy):
    universe = ["SPY"]
    options_on = ["SPY"]
    interval = "1d"
    params = {"dte": 30, "delta": 0.30}
    param_grid = {"delta": [0.15, 0.30, 0.50], "dte": [30, 45]}

    def on_bar(self, ctx):
        sym = self.universe[0]
        if ctx.position(sym):
            ctx.order_target(sym, 0)                        # assigned: sell the shares
            return
        if not ctx.options.positions(sym):
            put = ctx.options.select(sym, "P", self.params["dte"], delta=self.params["delta"])
            contracts = int(ctx.cash * 0.98 / (put.strike * 100))
            if contracts > 0:
                ctx.options.order(put, -contracts)
