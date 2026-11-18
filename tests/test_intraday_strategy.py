"""The engine strategy for intraday momentum must reproduce the exact-method returns, be flat at every close, and not look ahead."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtester.engine import CostModel, RunConfig, run_backtest
from tests.test_intraday_halfhours import day_bars, hh

FOLDER = Path(__file__).resolve().parent.parent / "strategies" / "intraday_momentum"


def load_strategy():
    spec = importlib.util.spec_from_file_location("intraday_strategy_under_test", FOLDER / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.IntradayMomentum


def synthetic(n=150, beta=0.08, seed=11, start="2025-01-02"):
    """n trading days of 30-minute bars with a planted relation r13 = beta r1 + noise."""
    rng = np.random.default_rng(seed)
    frames, prev = [], 400.0
    for d in pd.bdate_range(start, periods=n):
        r = rng.normal(0, 0.002, 13)
        r[0] = rng.normal(0, 0.006)
        r[12] = beta * r[0] + rng.normal(0, 0.003)
        prices = prev * np.cumprod(1 + r)
        frames.append(day_bars(d.strftime("%Y-%m-%d"), list(prices)))
        prev = prices[-1]
    return pd.concat(frames)


def run(bars, params=None, **cfg):
    cfg = {"fill": "close", "fractional_shares": True, "costs": CostModel.zero(), "cash_interest": False, **cfg}
    strat = load_strategy()(**(params or {}))
    return run_backtest(strat, RunConfig(**cfg), data={"SPY": bars})


def exact_returns(bars):
    p = hh.to_halfhours(bars)
    r = hh.returns(p)
    return p, r.dropna()


def daily_returns(result, tz="America/New_York"):
    eq = result.equity
    days = eq.index.tz_convert(tz).date
    daily = eq.groupby(days).last()
    return daily.pct_change()


def test_timing_strategy_earns_signal_times_the_last_half_hour():
    bars = synthetic()
    res = run(bars, {"signal": "r1", "mode": "timing"})
    p, r = exact_returns(bars)
    expected = np.where(r["r1"] > 0, 1, -1) * r["r13"]
    got = daily_returns(res).reindex(r.index)
    assert got.iloc[1:].to_numpy() == pytest.approx(expected.iloc[1:].to_numpy(), abs=1e-9)
    assert (res.fills["price"] > 0).all()


def test_two_signal_timing_stays_flat_when_the_signals_disagree():
    bars = synthetic(seed=3)
    res = run(bars, {"signal": "r1_r12", "mode": "timing"})
    p, r = exact_returns(bars)
    sig = np.select([(r["r1"] > 0) & (r["r12"] > 0), (r["r1"] <= 0) & (r["r12"] <= 0)], [1, -1], default=0)
    got = daily_returns(res).reindex(r.index)
    assert got.iloc[1:].to_numpy() == pytest.approx((sig * r["r13"]).iloc[1:].to_numpy(), abs=1e-9)
    assert (sig == 0).any()


def test_the_account_is_flat_after_every_close():
    res = run(synthetic(n=60), {"signal": "r1", "mode": "timing"})
    f = res.fills.copy()
    f["day"] = pd.to_datetime(f["time"], utc=True).dt.tz_convert("America/New_York").dt.date
    assert (f.groupby("day")["qty"].sum().abs() < 1e-9).all()                      # every day's trades net to zero
    assert abs(res.gross_exposure.iloc[-1]) < 1e-12


def test_entry_is_at_1530_and_exit_at_the_close():
    bars = synthetic(n=20)
    res = run(bars, {"signal": "r1", "mode": "timing"})
    t = pd.to_datetime(res.fills["time"], utc=True).dt.tz_convert("America/New_York")
    assert set(t.dt.strftime("%H:%M")) == {"15:00", "15:30"}                       # bar start labels: the entry bar (15:00-15:30) and the last bar


def test_mean_variance_mode_reproduces_the_exact_method_weights():
    bars = synthetic(n=260, beta=0.2, seed=5)
    res = run(bars, {"signal": "r1", "mode": "mean_variance", "min_obs": 60}, max_leverage=1.5)   # the paper allows 150% in the market
    p, r = exact_returns(bars)
    first_of_month = {}
    for d in r.index:
        first_of_month.setdefault((d.year, d.month), d)
    start = next(first for key, first in first_of_month.items() if sum(1 for d in r.index if d < first) >= 60)
    f = predict_module().recursive_forecast(r["r13"], r[["r1"]], start)
    w = np.clip(f["rhat"] / (5 * f["sigma2"]), -0.5, 1.5)
    got = daily_returns(res).reindex(f.index)
    assert got.to_numpy() == pytest.approx((w * f["y"]).to_numpy(), abs=1e-9)
    assert (w.abs() > 0.05).mean() > 0.5                                           # it really trades, not just zeros


def predict_module():
    sys.path.insert(0, str(FOLDER))
    spec = importlib.util.spec_from_file_location("intraday_predict_for_strategy_test", FOLDER / "predict.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_truncating_the_future_does_not_change_earlier_orders():
    bars = synthetic(n=120, seed=8)
    full = run(bars, {"signal": "r1_r12", "mode": "timing"}).orders
    cut = bars[bars.index < bars.index[len(bars) // 2]]
    part = run(cut, {"signal": "r1_r12", "mode": "timing"}).orders
    k = len(part)
    assert k > 5
    assert full.iloc[:k - 1][["time", "symbol", "qty"]].reset_index(drop=True).equals(part.iloc[:k - 1][["time", "symbol", "qty"]].reset_index(drop=True))


def test_half_days_are_skipped_and_never_leave_a_position():
    full = synthetic(n=40, seed=2)
    half = day_bars("2026-11-27", [100 + 0.1 * i for i in range(7)])                # a 13:00 close
    bars = pd.concat([full, half]).sort_index()
    res = run(bars, {"signal": "r1", "mode": "timing"})
    assert abs(res.gross_exposure.iloc[-1]) < 1e-12


def test_costs_are_charged_from_the_cost_model():
    bars = synthetic(n=40)
    free = run(bars, {"signal": "r1", "mode": "timing"})
    costly = run(bars, {"signal": "r1", "mode": "timing"}, costs=CostModel(slippage_bps=1.0, sell_value_fee=0.0000206))
    assert costly.equity.iloc[-1] < free.equity.iloc[-1]
    assert costly.fills["commission"].sum() > 0
