import math

import numpy as np
import pandas as pd
import pytest

from backtester.analysis.metrics import (compute_metrics, daily_equity, longest_drawdown_days,
                                         max_drawdown)
from backtester.engine.result import FILL_COLUMNS, ORDER_COLUMNS, TRADE_COLUMNS, RunResult


def result_from_equity(values, initial=100.0, trades=None, freq="B"):
    idx = pd.date_range("2024-01-02 14:30", periods=len(values), freq=freq, tz="UTC")
    eq = pd.Series(np.asarray(values, float), index=idx)
    return RunResult(
        equity=eq, gross_exposure=pd.Series(1.0, index=idx),
        fills=pd.DataFrame(columns=FILL_COLUMNS).astype({"qty": float, "price": float,
                                                         "commission": float, "slippage_cost": float}),
        trades=pd.DataFrame(trades or [], columns=TRADE_COLUMNS).astype({"pnl": float, "return": float}),
        orders=pd.DataFrame(columns=ORDER_COLUMNS),
        meta={"config": {"initial_cash": initial, "timezone": "America/New_York"}})


def test_max_drawdown_known_values():
    assert max_drawdown(np.array([100, 120, 90, 130, 117.0])) == pytest.approx(-0.25)
    assert max_drawdown(np.array([1, 2, 3.0])) == 0.0


def test_longest_drawdown_counts_calendar_days():
    idx = pd.date_range("2024-01-01", periods=8, freq="D", tz="UTC")
    eq = pd.Series([10, 12, 11, 10, 12, 13, 12, 12.5], index=idx)
    assert longest_drawdown_days(eq) == 3          # peak on day 1, recovered on day 4
    assert longest_drawdown_days(pd.Series([1, 2, 3.0], index=idx[:3])) == 0


def test_return_statistics_on_a_known_series():
    # +1% then -1% alternating for 252 days, starting from 100
    rets = np.tile([0.01, -0.01], 126)
    values = 100 * np.cumprod(1 + rets)
    m = compute_metrics(result_from_equity(values))
    assert m["trading_days"] == 252
    assert m["total_return"] == pytest.approx(values[-1] / 100 - 1)
    assert m["cagr"] == pytest.approx(m["total_return"])          # exactly one year
    sd = rets.std(ddof=1)
    assert m["volatility"] == pytest.approx(sd * math.sqrt(252))
    assert m["sharpe"] == pytest.approx(rets.mean() / sd * math.sqrt(252))
    assert m["worst_day"] == pytest.approx(-0.01)


def test_constant_growth_has_no_drawdown_and_doubles():
    daily = 2 ** (1 / 504) - 1                                    # doubles in two years
    values = 100 * (1 + daily) ** np.arange(1, 505)
    m = compute_metrics(result_from_equity(values))
    assert m["total_return"] == pytest.approx(1.0)
    assert m["cagr"] == pytest.approx(math.sqrt(2) - 1)
    assert m["max_drawdown"] == 0.0
    assert m["calmar"] is None and m["sortino"] is None           # undefined without losses


def test_risk_free_rate_lowers_sharpe():
    rng = np.random.default_rng(1)
    values = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 500))
    r = result_from_equity(values)
    assert compute_metrics(r, 0.04)["sharpe"] < compute_metrics(r, 0.0)["sharpe"]
    gap = compute_metrics(r, 0.0)["sharpe"] - compute_metrics(r, 0.04)["sharpe"]
    assert gap == pytest.approx(0.04 / compute_metrics(r)["volatility"])


def test_trade_statistics():
    t0 = pd.Timestamp("2024-01-02", tz="UTC")
    rows = [("A", "long", 1, t0, t0, 10, 13, 300.0, 0.3, 0), ("A", "long", 1, t0, t0, 10, 9, -100.0, -0.1, 0),
            ("A", "long", 1, t0, t0, 10, 11, 100.0, 0.1, 0), ("A", "long", 1, t0, t0, 10, 9, -100.0, -0.1, 0)]
    m = compute_metrics(result_from_equity([100, 101, 102], trades=rows))
    assert m["trades"] == 4
    assert m["win_rate"] == 0.5
    assert m["profit_factor"] == pytest.approx(2.0)
    assert m["expectancy"] == pytest.approx(50.0)
    assert m["avg_win"] == pytest.approx(200.0) and m["avg_loss"] == pytest.approx(-100.0)


def test_no_trades_gives_undefined_not_errors():
    m = compute_metrics(result_from_equity([100, 100, 100]))
    assert m["trades"] == 0 and m["win_rate"] is None and m["sharpe"] is None


def test_benchmark_beta_and_alpha():
    rng = np.random.default_rng(2)
    b_rets = rng.normal(0.0004, 0.01, 400)
    bench = 50 * np.cumprod(1 + b_rets)
    strat = 100 * np.cumprod(1 + 2 * b_rets)                      # exactly twice the benchmark's moves
    r = result_from_equity(strat)
    m = compute_metrics(r, benchmark=pd.Series(bench, index=r.equity.index))
    assert m["beta"] == pytest.approx(2.0)
    assert m["alpha_annual"] == pytest.approx(0.0, abs=1e-9)
    assert m["benchmark_total_return"] == pytest.approx(bench[-1] / bench[0] - 1)


def test_intraday_equity_is_reduced_to_one_value_per_trading_day():
    idx = pd.date_range("2024-01-02 14:30", periods=3, freq="5min", tz="UTC").append(
        pd.date_range("2024-01-03 14:30", periods=3, freq="5min", tz="UTC"))
    d = daily_equity(pd.Series([1, 2, 3, 4, 5, 6.0], index=idx))
    assert d.tolist() == [3.0, 6.0]
