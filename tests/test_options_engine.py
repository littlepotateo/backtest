"""Tests for the option chain and option positions inside the engine."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from backtester import Strategy
from backtester.analysis import checks
from backtester.engine import CostModel, RunConfig, Runner
from backtester.options import pricing as bs
from backtester.options.chain import OptionContract, OptionModel, third_friday
from backtester.options.surface import SurfaceParams, VolSurface

FLAT = SurfaceParams(ratio=1.0, skew=0.0, curvature=0.0, term=0.0, half_spread=0.0, min_half_spread=0.0)
JAN, FEB = dt.date(2024, 1, 19), dt.date(2024, 2, 16)


def level(v=0.2):
    return pd.Series(v, index=pd.date_range("2023-01-01", "2025-12-31"))


def model(params=FLAT, v=0.2):
    return OptionModel("A", VolSurface(params, level(v), "test"))


def runner(cls, data, params=FLAT, v=0.2, **cfg):
    cfg.setdefault("costs", CostModel.zero())
    cfg.setdefault("option_fee_per_contract", 0.0)
    cfg.setdefault("option_fee_min_per_order", 0.0)
    return Runner(cls, RunConfig(**cfg), data=data, option_levels={"A": level(v)}, option_params={"A": params})


class Script(Strategy):
    """Runs `script[bar]` = list of ("opt", contract, contracts) or ("stk", shares)."""
    universe = ["A"]
    options_on = ["A"]
    params = {"script": {}}

    def init(self, ctx):
        self.i = -1

    def on_bar(self, ctx):
        self.i += 1
        for step in self.params["script"].get(self.i, []):
            if step[0] == "opt":
                ctx.options.order(step[1], step[2])
            else:
                ctx.order("A", step[1])


def flat_then(bars, n_flat, *tail, price=100.0):
    """`n_flat` bars at `price`, then the given closes; opens equal the previous close."""
    return bars(np.concatenate([np.full(n_flat, price), np.array(tail, dtype=float)]))


def test_third_friday_and_chain():
    assert third_friday(2024, 1) == JAN and third_friday(2026, 11) == dt.date(2026, 11, 20)
    m = model()
    exp = m.expiries(pd.Timestamp("2024-01-02 14:30", tz="UTC"))
    assert exp[0] == JAN and exp[1] == FEB and all(e.weekday() == 4 for e in exp)
    assert m.expiries(pd.Timestamp("2024-01-22", tz="UTC"))[0] == FEB        # January has passed
    k = m.strikes(100.0)
    assert 100.0 in k and k.min() <= 50 and k.max() >= 150 and np.allclose(np.diff(k), 1.0)
    weekly = OptionModel("A", VolSurface(FLAT, level(), "t"), weeklies=True)
    assert dt.date(2024, 1, 5) in weekly.expiries(pd.Timestamp("2024-01-02", tz="UTC"))


def test_select_by_delta_strike_and_percent():
    m, now = model(), pd.Timestamp("2024-01-02 21:00", tz="UTC")
    c = m.select(now, 100.0, "C", 45, delta=0.30)
    assert c.expiry == FEB and c.right == "C" and c.strike > 100
    assert abs(m.greeks(c, 100.0, now)["delta"]) == pytest.approx(0.30, abs=0.06)
    p = m.select(now, 100.0, "P", 17, delta=0.30)
    assert p.expiry == JAN and p.strike < 100
    assert m.select(now, 100.0, "C", 17, strike=103.4).strike == 103
    assert m.select(now, 100.0, "P", 17, pct=0.95).strike == 95
    with pytest.raises(ValueError):
        m.select(now, 100.0, "C", 30)
    with pytest.raises(ValueError):
        m.select(now, 100.0, "C", 30, delta=0.3, strike=100)
    assert str(c).startswith("A 2024-02-16 C")


def test_model_value_matches_black_scholes_and_opening_uses_yesterdays_level():
    lv = level(0.2)
    lv.loc["2024-01-10":] = 0.6                                   # volatility jumps on the 10th
    m = OptionModel("A", VolSurface(FLAT, lv, "t"))
    c = OptionContract("A", FEB, 100.0, "C")
    close9 = pd.Timestamp("2024-01-09 21:00", tz="UTC")
    days = (FEB - dt.date(2024, 1, 9)).days
    assert m.value(c, 100.0, close9) == pytest.approx(bs.price(100, 100, days / 365, 0, 0, 0.2, "C"))
    open10 = pd.Timestamp("2024-01-10 14:30", tz="UTC")
    expected = bs.price(100, 100, (days - 1 + 0.27) / 365, 0, 0, 0.2, "C")   # still the old level
    assert m.value(c, 100.0, open10, at_open=True) == pytest.approx(expected)
    assert m.value(c, 100.0, pd.Timestamp("2024-01-10 21:00", tz="UTC")) > 2 * expected
    assert m.value(c, 108.0, pd.Timestamp("2024-02-16 21:00", tz="UTC")) == 8.0   # intrinsic at expiry


def test_long_call_held_to_expiry_settles_in_cash(bars):
    call = OptionContract("A", JAN, 100.0, "C")
    data = {"A": flat_then(bars, 13, 110.0)}                      # bar 13 is Friday 19 January
    assert data["A"].index[13].date() == JAN
    res = runner(Script, data).run({"script": {0: [("opt", call, 2)]}})
    paid = res.fills.iloc[0]["price"]
    t = ((JAN - dt.date(2024, 1, 3)).days + 0.27) / 365
    assert paid == pytest.approx(bs.price(100, 100, t, 0, 0, 0.2, "C"))
    assert res.fills.iloc[0]["qty"] == 200                         # share-equivalents
    assert res.equity.iloc[-1] == pytest.approx(100_000 + 200 * (10.0 - paid))
    assert res.meta["options"]["open_positions"] == {}
    tr = res.trades.iloc[0]
    assert tr["pnl"] == pytest.approx(200 * (10.0 - paid)) and tr["side"] == "long"
    assert res.meta["open_positions"] == {}                        # no shares: long options settle in cash


def test_covered_call_assignment_removes_shares_at_the_strike(bars):
    call = OptionContract("A", JAN, 105.0, "C")
    data = {"A": flat_then(bars, 13, 112.0)}
    res = runner(Script, data).run({"script": {0: [("stk", 100), ("opt", call, -1)]}})
    premium = res.fills[res.fills["symbol"] == str(call)].iloc[0]["price"]
    # shares bought at 100 and called away at 105, plus the premium kept
    assert res.equity.iloc[-1] == pytest.approx(100_000 + 100 * (105 - 100) + 100 * premium)
    assert res.meta["open_positions"] == {} and res.meta["options"]["open_positions"] == {}
    assert any(r["name"] == "assigned_at_expiry" for r in res.meta["records"])
    assert res.trades["pnl"].sum() == pytest.approx(res.equity.iloc[-1] - 100_000)   # P&L reconciles
    # out of the money: keep shares and premium
    data2 = {"A": flat_then(bars, 13, 103.0)}
    res2 = runner(Script, data2).run({"script": {0: [("stk", 100), ("opt", call, -1)]}})
    assert res2.meta["open_positions"] == {"A": 100.0}
    assert res2.equity.iloc[-1] == pytest.approx(100_000 + 100 * 3 + 100 * premium)


def test_cash_secured_put_assignment_buys_shares(bars):
    put = OptionContract("A", JAN, 95.0, "P")
    data = {"A": flat_then(bars, 13, 90.0)}
    res = runner(Script, data).run({"script": {0: [("opt", put, -3)]}})
    premium = res.fills.iloc[0]["price"]
    assert res.meta["open_positions"] == {"A": 300.0}
    assert res.equity.iloc[-1] == pytest.approx(100_000 + 300 * premium - 300 * (95 - 90))


def test_only_defined_risk_books_are_accepted(bars):
    data = {"A": flat_then(bars, 13, 100.0)}
    call, put = OptionContract("A", JAN, 105.0, "C"), OptionContract("A", JAN, 95.0, "P")

    def run(script, cash=100_000):
        return runner(Script, data, initial_cash=cash).run({"script": {0: script}})

    naked = run([("opt", call, -1)])
    assert naked.fills.empty and naked.meta["warnings"]["option_orders_rejected"] == 1
    assert "uncovered short call" in naked.meta["records"][0]["value"]
    assert len(run([("stk", 100), ("opt", call, -1)]).fills) == 2             # covered: fine
    assert run([("stk", 100), ("opt", call, -2)]).meta["warnings"]["option_orders_rejected"] == 1
    assert len(run([("opt", put, -1)]).fills) == 1                            # cash-secured: fine
    poor = run([("opt", put, -1)], cash=5_000)                                # 9,500 needed
    assert poor.fills.empty and "more than the account holds" in poor.meta["records"][0]["value"]
    spread = [("opt", OptionContract("A", JAN, 110.0, "C"), 1), ("opt", call, -1)]
    assert len(run(spread, cash=1_000).fills) == 2                            # 500 at risk: fine
    assert run(spread, cash=300).fills.empty                                  # cannot cover 500
    assert len(run([("opt", call, 5)]).fills) == 1                            # buying is always defined-risk


def test_iron_condor_loss_is_capped_at_the_wing_width(bars):
    legs = [("opt", OptionContract("A", JAN, 90.0, "P"), 2), ("opt", OptionContract("A", JAN, 110.0, "C"), 2),
            ("opt", OptionContract("A", JAN, 95.0, "P"), -2), ("opt", OptionContract("A", JAN, 105.0, "C"), -2)]
    crash = runner(Script, {"A": flat_then(bars, 13, 60.0)}).run({"script": {0: legs}})
    f = crash.fills
    credit = -(f["qty"] * f["price"]).sum()
    assert credit > 0
    assert crash.equity.iloc[-1] == pytest.approx(100_000 + credit - 200 * 5)      # width 5, two condors
    assert crash.meta["open_positions"] == {}                                  # spreads settle in cash
    calm = runner(Script, {"A": flat_then(bars, 13, 100.0)}).run({"script": {0: legs}})
    assert calm.equity.iloc[-1] == pytest.approx(100_000 + credit)             # keeps the whole credit
    spike = runner(Script, {"A": flat_then(bars, 13, 160.0)}).run({"script": {0: legs}})
    assert spike.equity.iloc[-1] == pytest.approx(100_000 + credit - 200 * 5)


def test_fees_spread_and_reconciliation(bars):
    call = OptionContract("A", FEB, 100.0, "C")
    data = {"A": flat_then(bars, 20, 101, 99, 102, 100)}
    script = {0: [("opt", call, 3)], 10: [("opt", call, -3)]}
    params = SurfaceParams(ratio=1.0, skew=0.0, curvature=0.0, term=0.0, half_spread=0.02, min_half_spread=0.01)
    free = runner(Script, data).run({"script": script})
    paid = runner(Script, data, params=params, option_fee_per_contract=0.65,
                  option_fee_min_per_order=1.0).run({"script": script})
    f = paid.fills
    assert f["commission"].tolist() == pytest.approx([1.95, 1.95])             # 3 x 0.65
    assert f.iloc[0]["price"] > free.fills.iloc[0]["price"]                    # buys above mid
    assert f.iloc[1]["price"] < free.fills.iloc[1]["price"]                    # sells below mid
    costs = f["commission"].sum() + f["slippage_cost"].sum()
    assert free.equity.iloc[-1] - paid.equity.iloc[-1] == pytest.approx(costs)
    assert paid.trades["pnl"].sum() == pytest.approx(paid.equity.iloc[-1] - 100_000)
    assert paid.trades["costs"].sum() == pytest.approx(costs)
    one = runner(Script, data, option_fee_per_contract=0.65, option_fee_min_per_order=1.0) \
        .run({"script": {0: [("opt", call, 1)]}})
    assert one.fills.iloc[0]["commission"] == pytest.approx(1.0)               # minimum per order


def test_positions_are_marked_to_model_each_bar(bars):
    call = OptionContract("A", FEB, 100.0, "C")
    data = {"A": flat_then(bars, 5, 104.0, 104.0)}
    res = runner(Script, data).run({"script": {0: [("opt", call, 1)]}})
    m = model()
    t = data["A"].index[5]
    paid = res.fills.iloc[0]["price"]
    assert res.equity.loc[t] == pytest.approx(100_000 + 100 * (m.value(call, 104.0, t) - paid))


def test_early_assignment_before_a_dividend(bars):
    df = flat_then(bars, 6, 120.0, 120.0, 120.0, 120.0)
    df["adj_factor"] = 1.0
    df.iloc[:8, df.columns.get_loc("adj_factor")] = 0.975          # 3.00 dividend, ex on bar 8
    call = OptionContract("A", FEB, 100.0, "C")                    # deep in the money, little time value
    res = runner(Script, {"A": df}).run({"script": {0: [("stk", 100), ("opt", call, -1)]}})
    names = [r["name"] for r in res.meta["records"]]
    assert "assigned_early_before_dividend" in names
    assert res.meta["open_positions"] == {} and res.meta["dividends_received"] == 0   # shares gone first


def test_options_strategy_passes_the_lookahead_test(bars):
    rng = np.random.default_rng(0)
    data = {"A": bars(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 260))))}

    class Monthly(Strategy):
        universe = ["A"]
        options_on = ["A"]

        def on_bar(self, ctx):
            if ctx.position("A") < 100:
                ctx.order_target("A", 100)
            elif not ctx.options.positions("A"):
                ctx.options.order(ctx.options.select("A", "C", 30, delta=0.3), -1)

    r = runner(Monthly, data, params=SurfaceParams())
    res = r.run()
    assert len(res.trades) >= 8 and res.meta["options"]["underlyings"]["A"]["volatility_source"] == "supplied"
    assert checks.lookahead_test(r)["passed"]
    assert res.meta["config"]["use_adjusted"] is False              # options run on real prices
