"""Iron condor: each month sell a put and a call at about `delta` and buy protection
`width` percent of the price further out on each side. Risk per condor is the width
minus the credit; `risk` is the share of equity put at risk each month. Held to expiry."""

from backtester import Strategy


class IronCondor(Strategy):
    universe = ["SPY"]
    options_on = ["SPY"]
    interval = "1d"
    params = {"dte": 30, "delta": 0.16, "width": 0.03, "risk": 0.10}
    param_grid = {"delta": [0.10, 0.16, 0.25], "width": [0.02, 0.03, 0.05]}

    def on_bar(self, ctx):
        sym = self.universe[0]
        if ctx.options.positions(sym):
            return
        p = self.params
        spot = ctx.price(sym)
        short_put = ctx.options.select(sym, "P", p["dte"], delta=p["delta"])
        short_call = ctx.options.select(sym, "C", p["dte"], delta=p["delta"])
        long_put = ctx.options.select(sym, "P", p["dte"], strike=short_put.strike - spot * p["width"])
        long_call = ctx.options.select(sym, "C", p["dte"], strike=short_call.strike + spot * p["width"])
        wing = max(short_put.strike - long_put.strike, long_call.strike - short_call.strike)
        if wing <= 0:
            return
        n = int(ctx.equity * p["risk"] / (wing * 100))
        if n > 0:
            for contract, qty in ((long_put, n), (long_call, n), (short_put, -n), (short_call, -n)):
                ctx.options.order(contract, qty)
