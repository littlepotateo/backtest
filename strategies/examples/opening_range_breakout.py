"""Opening-range breakout on intraday bars.

Each day: note the high and low of the first `range_bars` bars. Go long on a close above
that high, short on a close below that low (one entry per day). Exit on the opposite
side of the range (stop) or shortly before the close.
"""

from backtester import Strategy


class OpeningRangeBreakout(Strategy):
    universe = ["SPY"]
    interval = "5m"
    params = {"range_bars": 6, "allow_short": True}

    def init(self, ctx):
        self.day = None

    def on_bar(self, ctx):
        symbol = self.universe[0]
        if not ctx.has_bar(symbol):
            return
        if ctx.session_date(symbol) != self.day:
            self.day = ctx.session_date(symbol)
            self.high = self.low = None
            self.traded = False
        n = self.params["range_bars"]
        into = ctx.bars_into_session(symbol)
        position = ctx.position(symbol)

        if into == n - 1:
            bars = ctx.history(symbol, n)
            self.high, self.low = bars["high"].max(), bars["low"].min()
            return
        if self.high is None:
            return

        close = ctx.price(symbol)
        if ctx.bars_left_in_session(symbol) <= 1:
            if position:
                ctx.order_target(symbol, 0)      # fills at the open of the day's last bar
            return
        if position > 0 and close < self.low or position < 0 and close > self.high:
            ctx.order_target(symbol, 0)
        elif position == 0 and not self.traded:
            if close > self.high:
                ctx.order_target_percent(symbol, 1.0)
                self.traded = True
            elif close < self.low and self.params["allow_short"]:
                ctx.order_target_percent(symbol, -1.0)
                self.traded = True
