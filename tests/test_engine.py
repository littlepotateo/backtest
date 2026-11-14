import numpy as np
import pandas as pd
import pytest

from backtester import Strategy
from backtester.engine import CostModel, RunConfig, RunResult, get_backend, run_backtest

ZERO = CostModel.zero()


class BuyAndHold(Strategy):
    universe = ["A"]

    def on_bar(self, ctx):
        if ctx.position("A") == 0:
            ctx.order_target_percent("A", 1.0)


class Scripted(Strategy):
    """Places order(symbol, qty) at given bar numbers: {bar: [(symbol, qty), ...]}."""
    universe = ["A"]
    params = {"script": {}}

    def init(self, ctx):
        self.i = -1
        self.seen = []

    def on_bar(self, ctx):
        self.i += 1
        self.seen.append((ctx.now, len(ctx.history("A")), ctx.price("A")))
        for symbol, qty in self.params["script"].get(self.i, []):
            ctx.order(symbol, qty)


def run(strategy, data, **cfg):
    cfg.setdefault("costs", ZERO)
    return run_backtest(strategy, RunConfig(**cfg), data=data)


def test_buy_and_hold_matches_asset_return(bars):
    data = {"A": bars([100, 102, 101, 105, 110], opens=[100, 100, 103, 101, 106])}
    r = run(BuyAndHold(), data, fractional_shares=True)
    # order placed after bar 0 closes at 100 -> 1000 shares, filled at bar 1's open of 100
    assert r.fills.iloc[0]["price"] == 100
    assert r.fills.iloc[0]["time"] == data["A"].index[1]
    assert r.equity.iloc[-1] == pytest.approx(100_000 * 110 / 100)
    assert r.equity.iloc[0] == 100_000


def test_orders_fill_at_next_bar_open_not_same_bar(bars):
    data = {"A": bars([10, 20, 30, 40], opens=[10, 11, 21, 31])}
    r = run(Scripted(script={0: [("A", 100)], 2: [("A", -100)]}), data)
    assert list(r.fills["price"]) == [11, 31]
    assert list(r.fills["time"]) == [data["A"].index[1], data["A"].index[3]]
    assert r.trades.iloc[0]["pnl"] == pytest.approx(100 * (31 - 11))
    assert r.equity.iloc[-1] == pytest.approx(100_000 + 2000)


def test_fill_at_close_mode_is_flagged(bars):
    data = {"A": bars([10, 20, 30], opens=[10, 11, 21])}
    r = run(Scripted(script={0: [("A", 100)]}), data, fill="close")
    assert r.fills.iloc[0]["price"] == 10
    assert any("optimistic" in n for n in r.meta["notes"])


def test_strategy_never_sees_future_bars(bars):
    data = {"A": bars(np.arange(10, 20))}
    s = Scripted()
    run(s, data)
    for k, (now, n_hist, price) in enumerate(s.seen):
        assert n_hist == k + 1
        assert now == data["A"].index[k]
        assert price == data["A"]["close"].iloc[k]


def test_truncating_future_data_does_not_change_past_orders(bars):
    rng = np.random.default_rng(0)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))

    class Momentum(Strategy):
        universe = ["A"]

        def on_bar(self, ctx):
            c = ctx.closes("A", 20)
            if len(c) == 20:
                ctx.order_target_percent("A", 1.0 if c[-1] > c.mean() else 0.0)

    full = run(Momentum(), {"A": bars(closes)})
    cut = run(Momentum(), {"A": bars(closes[:200])})
    k = len(cut.fills)
    assert k > 5
    pd.testing.assert_frame_equal(full.fills.iloc[:k], cut.fills)
    pd.testing.assert_series_equal(full.equity.iloc[:200], cut.equity)


def test_costs_reduce_pnl_by_exactly_the_recorded_costs(bars):
    data = {"A": bars([50, 51, 52, 53, 54, 55], opens=[50, 50, 51, 52, 53, 54])}
    script = {0: [("A", 300)], 2: [("A", -100)], 3: [("A", -200)]}
    free = run(Scripted(script=script), data)
    costs = CostModel(per_share=0.005, min_per_order=1.0, max_pct_of_trade=0.01, slippage_bps=5)
    paid = run(Scripted(script=script), data, costs=costs)
    recorded = paid.fills["commission"].sum() + paid.fills["slippage_cost"].sum()
    assert recorded > 0
    assert free.equity.iloc[-1] - paid.equity.iloc[-1] == pytest.approx(recorded)
    # trade P&L net of costs adds up to the change in equity (all positions closed)
    assert paid.trades["pnl"].sum() == pytest.approx(paid.equity.iloc[-1] - 100_000)
    assert paid.trades["costs"].sum() == pytest.approx(recorded)


def test_commission_minimum_normal_and_cap():
    c = CostModel(per_share=0.005, min_per_order=1.0, max_pct_of_trade=0.01, slippage_bps=0)
    assert c.commission(100, 50) == pytest.approx(1.0)        # 0.50 -> minimum 1.00
    assert c.commission(1000, 50) == pytest.approx(5.0)       # 1000 x 0.005
    assert c.commission(100, 0.5) == pytest.approx(0.5)       # capped at 1% of $50
    assert c.scaled(2).commission(1000, 50) == pytest.approx(10.0)
    assert c.commission(0, 50) == 0
    s = CostModel(slippage_bps=10)
    assert s.fill_price(100, +1) == pytest.approx(100.10)
    assert s.fill_price(100, -1) == pytest.approx(99.90)


def test_short_position_profit_and_loss(bars):
    data = {"A": bars([100, 100, 90, 90], opens=[100, 100, 100, 90])}
    r = run(Scripted(script={0: [("A", -100)], 2: [("A", 100)]}), data)
    assert r.trades.iloc[0]["side"] == "short"
    assert r.trades.iloc[0]["pnl"] == pytest.approx(1000)
    assert r.equity.iloc[-1] == pytest.approx(101_000)
    blocked = run(Scripted(script={0: [("A", -100)]}), data, allow_short=False)
    assert blocked.fills.empty and blocked.meta["warnings"]["short_orders_blocked"] == 1


def test_reversal_closes_then_opens(bars):
    data = {"A": bars([10, 10, 12, 12, 9], opens=[10, 10, 10, 12, 12])}
    r = run(Scripted(script={0: [("A", 100)], 2: [("A", -250)], 3: [("A", 150)]}), data)
    assert list(r.trades["side"]) == ["long", "short"]
    assert list(r.trades["qty"]) == [100, 150]
    assert r.trades["pnl"].tolist() == pytest.approx([200, 0])


def test_buying_power_limits_position_size(bars):
    data = {"A": bars([100, 100, 100], opens=[100, 110, 100])}
    r = run(Scripted(script={0: [("A", 1000)]}), data)      # wants $110k of stock with $100k
    assert r.fills.iloc[0]["qty"] == 909                      # floor(100000 / 110)
    assert r.meta["warnings"]["orders_reduced_for_buying_power"] == 1
    lev = run(Scripted(script={0: [("A", 1000)]}), data, max_leverage=2.0)
    assert lev.fills.iloc[0]["qty"] == 1000


def test_whole_shares_by_default(bars):
    data = {"A": bars([30, 30, 30])}
    r = run(BuyAndHold(), data, initial_cash=100)
    assert r.fills.iloc[0]["qty"] == 3


def test_multiple_symbols_with_different_calendars(bars):
    a = bars([10, 11, 12, 13, 14])
    b = bars([20, 22, 24, 26, 28]).iloc[[0, 2, 4]]            # B trades every other day

    class Two(Strategy):
        universe = ["A", "B"]

        def init(self, ctx):
            self.done = False

        def on_bar(self, ctx):
            if not self.done:
                ctx.order("A", 10)
                ctx.order("B", 10)
                self.done = True

    r = run(Two(), {"A": a, "B": b})
    fills = r.fills.set_index("symbol")
    assert fills.loc["A", "time"] == a.index[1]
    assert fills.loc["B", "time"] == b.index[1]               # waits for B's next bar
    assert r.equity.iloc[-1] == pytest.approx(100_000 + 10 * (14 - 10) + 10 * (28 - 22))   # B filled at its open of 22


def test_start_date_gives_warmup_history_without_trading(bars):
    data = {"A": bars(np.arange(100, 130))}
    s = Scripted()
    start = data["A"].index[10]
    r = run(s, data, start=start.strftime("%Y-%m-%d"))
    assert r.equity.index[0] == start
    assert s.seen[0][1] == 11                                  # ten earlier bars visible
    assert len(r.equity) == 20


def test_end_date_is_inclusive(bars):
    data = {"A": bars(np.arange(100, 130))}
    end = data["A"].index[5]
    r = run(Scripted(), data, end=end.strftime("%Y-%m-%d"))
    assert r.equity.index[-1] == end


def test_adjusted_prices_are_used_by_default(bars):
    df = bars([100, 100, 100, 100])
    df["adj_factor"] = [0.5, 0.5, 1.0, 1.0]                   # e.g. a large dividend
    adj = run(BuyAndHold(), {"A": df}, fractional_shares=True)
    raw = run(BuyAndHold(), {"A": df}, fractional_shares=True, use_adjusted=False)
    assert adj.equity.iloc[-1] == pytest.approx(200_000)
    assert raw.equity.iloc[-1] == pytest.approx(150_000)        # price flat, 50 a share paid in cash
    assert raw.meta["dividends_received"] == pytest.approx(50_000)
    bare = run(BuyAndHold(), {"A": df}, fractional_shares=True, use_adjusted=False, pay_dividends=False)
    assert bare.equity.iloc[-1] == pytest.approx(100_000)


def test_intraday_session_helpers():
    idx = pd.date_range("2024-01-02 14:30", periods=4, freq="5min", tz="UTC").append(
        pd.date_range("2024-01-03 14:30", periods=3, freq="5min", tz="UTC"))
    from backtester.data.cache import normalise_bars
    df = normalise_bars(pd.DataFrame({"open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
                                      "volume": 1}, index=idx))
    seen = []

    class Watch(Strategy):
        universe = ["A"]
        interval = "5m"

        def on_bar(self, ctx):
            seen.append((ctx.bars_into_session("A"), ctx.bars_left_in_session("A"),
                         str(ctx.session_date("A"))))

    run(Watch(), {"A": df})
    assert [s[0] for s in seen] == [0, 1, 2, 3, 0, 1, 2]
    assert [s[1] for s in seen] == [3, 2, 1, 0, 2, 1, 0]
    assert seen[0][2] == "2024-01-02" and seen[-1][2] == "2024-01-03"


def test_unknown_parameter_and_symbol_are_rejected(bars):
    with pytest.raises(ValueError):
        Scripted(nope=1)
    with pytest.raises(KeyError):
        run(Scripted(script={0: [("ZZZ", 1)]}), {"A": bars([1, 2, 3])})
    with pytest.raises(ValueError):
        run(Scripted(), {})


def test_result_round_trips_through_disk(bars, tmp_path):
    data = {"A": bars([10, 20, 30, 40], opens=[10, 11, 21, 31])}
    r = run(Scripted(script={0: [("A", 100)], 2: [("A", -100)]}), data)
    loaded = RunResult.load(r.save(tmp_path / "run"))
    pd.testing.assert_series_equal(loaded.equity, r.equity, check_freq=False)
    assert loaded.trades["pnl"].tolist() == r.trades["pnl"].tolist()
    assert loaded.meta["backend"] == "native"


def test_lean_backend_is_a_declared_but_unbuilt_seam():
    assert get_backend("native").name == "native"
    with pytest.raises(NotImplementedError):
        get_backend("lean")
