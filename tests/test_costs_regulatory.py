"""IBKR regulatory and clearing fees on US stock and ETF trades (read from IBKR's commission page on 2026-11-18): the SEC transaction fee and
the FINRA trading activity fee apply to SALES only; the audit-trail and clearing fees to every share traded. Commission itself is zero (IBKR Lite)."""

import pytest

from backtester import Strategy
from backtester.engine import CostModel, RunConfig, run_backtest
from tests.test_engine import Scripted


def ibkr(**kw):
    base = dict(per_share=0.0, min_per_order=0.0, max_pct_of_trade=0.0, slippage_bps=0.0,
                sell_value_fee=0.0000206, sell_share_fee=0.000166, sell_share_fee_cap=8.30, share_fee=0.000003 + 0.0002)
    base.update(kw)
    return CostModel(**base)


def test_buys_pay_only_the_per_share_fees():
    assert ibkr().regulatory_fee(+100, 700.0) == pytest.approx(100 * 0.000203)


def test_sells_also_pay_the_sec_and_finra_fees():
    expected = 100 * 700.0 * 0.0000206 + 100 * 0.000166 + 100 * 0.000203
    assert ibkr().regulatory_fee(-100, 700.0) == pytest.approx(expected)


def test_the_finra_fee_has_a_cap_per_trade():
    capped = ibkr().regulatory_fee(-1_000_000, 10.0)
    assert capped == pytest.approx(1_000_000 * 10.0 * 0.0000206 + 8.30 + 1_000_000 * 0.000203)


def test_multiplier_scales_fees_and_zero_removes_them():
    assert ibkr().scaled(2.0).regulatory_fee(-100, 700.0) == pytest.approx(2 * ibkr().regulatory_fee(-100, 700.0))
    assert CostModel.zero().regulatory_fee(-100, 700.0) == 0.0


def test_the_toml_file_carries_the_ibkr_values(tmp_path):
    f = tmp_path / "costs.toml"
    f.write_text('confirmed = true\n[stock]\nper_share = 0.0\nsell_value_fee = 0.0000206\nsell_share_fee = 0.000166\n'
                 'sell_share_fee_cap = 8.30\nshare_fee = 0.000203\nslippage_bps = 0.6\n', encoding="utf-8")
    m = CostModel.from_toml(f)
    assert (m.sell_value_fee, m.sell_share_fee, m.sell_share_fee_cap, m.share_fee, m.slippage_bps) == (0.0000206, 0.000166, 8.30, 0.000203, 0.6)
    shipped = CostModel.from_toml("config/costs.toml")
    assert shipped.sell_value_fee == pytest.approx(0.0000206) and shipped.per_share == 0.0


def test_the_engine_charges_the_fees_on_each_fill(bars):
    data = {"A": bars([100, 100, 100, 100, 100], opens=[100] * 5)}
    r = run_backtest(Scripted(script={0: [("A", 100)], 2: [("A", -100)]}), RunConfig(costs=ibkr()), data=data)
    buy, sell = r.fills.iloc[0]["commission"], r.fills.iloc[1]["commission"]
    assert buy == pytest.approx(100 * 0.000203)
    assert sell == pytest.approx(100 * 100.0 * 0.0000206 + 100 * 0.000166 + 100 * 0.000203)
