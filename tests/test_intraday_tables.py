"""The exact-method table code must recover a relation planted in synthetic data (the paper's own data are not available)."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtester.engine import CostModel
from tests.test_intraday_halfhours import hh
from tests.test_intraday_strategy import synthetic

FOLDER = Path(__file__).resolve().parent.parent / "strategies" / "intraday_momentum"
sys.path.insert(0, str(FOLDER))
spec = importlib.util.spec_from_file_location("intraday_tables_under_test", FOLDER / "replicate_tables.py")
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)


@pytest.fixture(scope="module")
def data():
    bars = synthetic(n=900, beta=0.10, seed=21, start="2020-01-02")
    p = hh.to_halfhours(bars)
    return p, hh.returns(p)


def test_table1_recovers_the_planted_slope_and_has_positive_out_of_sample_r2(data):
    p, r = data
    t1 = T.table1(r, oos_start="2022-01-03")
    slope, tstat = t1["r1"]["r1"]
    assert slope == pytest.approx(10.0, abs=3.0) and tstat > 3                       # x100 scaling of the planted 0.10
    assert 0.5 < t1["r1"]["r2_pct"] < 6
    assert t1["r1"]["r2_oos_pct"] > 0.3 and abs(t1["r12"]["r12"][0]) < 8             # r12 carries nothing in this data


def test_table6_timing_beats_always_long_and_buy_and_hold_statistics_exist(data):
    p, r = data
    t6 = T.table6(p, r)
    assert t6["eta_r1"]["mean_pct"] > t6["always_long"]["mean_pct"] + 2
    assert t6["eta_r1"]["success_pct"] > 52
    assert t6["eta_r1_r12"]["success_pct"] > t6["eta_r1"]["success_pct"] - 5      # the combined rule is in the market less often
    assert {"mean_pct", "sd_pct", "sharpe", "skew", "kurtosis", "success_pct"} <= set(t6["buy_hold"])


def test_table7_mean_variance_investor_beats_the_historical_mean(data):
    p, r = data
    t7 = T.table7(r, oos_start="2022-01-03")
    assert t7["r1"]["cer_pct"] > 0 and t7["r1"]["sharpe"] > t7["r1"]["hist_sharpe"]


def test_table10_costs_reduce_the_return_by_spread_plus_fees(data):
    p, r = data
    costs = CostModel(sell_value_fee=0.0000206, sell_share_fee=0.000166, sell_share_fee_cap=8.30, share_fee=0.000203)
    t10 = T.table10(r, 0.6, costs, p["p12"])
    diff = t10["eta_r1"]["gross_mean_pct"] - t10["eta_r1"]["net_mean_pct"]
    assert diff == pytest.approx(t10["eta_r1"]["cost_pct_per_year"], rel=1e-6)
    per_trade = T.trade_cost_fraction(1, 400.0, 0.6e-4, costs)
    assert per_trade == pytest.approx(0.6e-4 + 0.0000206 + (0.000166 + 2 * 0.000203) / 400.0)
    assert 0.5 < diff < 3.0                                                             # about (0.6 + 0.2) bp x 252 = 2.0 percent a year
    wider = T.table10(r, 2.4, costs, p["p12"])["eta_r1"]["net_mean_pct"]
    assert wider < t10["eta_r1"]["net_mean_pct"]


def test_the_report_prints_every_table_with_the_paper_values_beside(data):
    p, r = data
    text = T.report(p, r, CostModel(slippage_bps=0.6), 0.6, oos_start="2022-01-03")
    for needle in ("TABLE 1", "TABLE 2", "TABLE 6", "TABLE 7", "TABLE 10", "6.94", "1.08", "Sample:"):
        assert needle in text
