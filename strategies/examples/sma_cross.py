"""Moving-average crossover: hold the asset while the fast average is above the slow one."""

from backtester import Strategy


class SmaCross(Strategy):
    universe = ["SPY"]
    interval = "1d"
    params = {"fast": 50, "slow": 200}
    param_grid = {"fast": [20, 50, 100], "slow": [100, 150, 200, 250]}

    @classmethod
    def valid_params(cls, params):
        return params["fast"] < params["slow"]

    def on_bar(self, ctx):
        symbol = self.universe[0]
        fast, slow = self.params["fast"], self.params["slow"]
        closes = ctx.closes(symbol, slow)
        if len(closes) < slow:
            return
        above = closes[-fast:].mean() > closes.mean()
        holding = ctx.position(symbol) > 0
        if above and not holding:
            ctx.order_target_percent(symbol, 1.0)
        elif not above and holding:
            ctx.order_target_percent(symbol, 0.0)
