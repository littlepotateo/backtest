"""Known-answer tests for the second pass on Zakamulin (2026): country files, the 18 portfolio datasets, diversified strategies,
and the rolling-start Sharpe ratios of Figures 1 and 2."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

FOLDER = Path(__file__).resolve().parent.parent / "strategies" / "regime_optimal"


def load(name):
    sys.path.insert(0, str(FOLDER))
    spec = importlib.util.spec_from_file_location(f"regime_optimal_x_{name}", FOLDER / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


french = load("french")
tables = load("replicate_tables")
div = load("diversified")

COUNTRY_DAT = (
    "\r\n"
    "     Value-Weight Dollar Returns      All 4 Data Items Not Reqd\r\n"
    "                -- BE/ME --   --- E/P ---\r\n"
    "          Mkt   High    Low   High    Low\r\n"
    "197501  25.01  27.27  28.72  30.82  25.75\r\n"
    "197502   2.17   2.43   1.84   4.71  -0.75\r\n"
    "197503-99.99  8.59   9.09   9.61   6.86\r\n"
    "\r\n"
    "     Value-Weight Local  Returns      All 4 Data Items Not Reqd\r\n"
    "                -- BE/ME --   --- E/P ---\r\n"
    "          Mkt   High    Low   High    Low\r\n"
    "197501  11.00  27.27  28.72  30.82  25.75\r\n"
)


def test_country_file_takes_the_first_dollar_block_market_column_and_marks_missing():
    s = french.parse_country_dat(COUNTRY_DAT)
    assert list(s.index.astype(str)) == ["1975-01", "1975-02", "1975-03"]
    assert s.iloc[0] == pytest.approx(0.2501) and s.iloc[1] == pytest.approx(0.0217)      # percent -> decimal, Dollar not Local
    assert np.isnan(s.iloc[2])                                                           # -99.99 means missing


PORTFOLIO_CSV = (
    "header text\n\n"
    "  Average Value Weighted Returns -- Monthly\n"
    ",SMALL LoBM,ME1 BM2,SMALL HiBM\n"
    "196307,  -1.50,   2.00,  -99.99\n"
    "196308,   4.00,   1.00,   3.00\n"
    "\n"
    "  Average Equal Weighted Returns -- Monthly\n"
    ",SMALL LoBM,ME1 BM2,SMALL HiBM\n"
    "196307,   9.00,   9.00,   9.00\n"
)


def test_portfolio_dataset_reads_the_value_weighted_block_only(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text(PORTFOLIO_CSV)
    df = french.parse_portfolio_csv(p)
    assert df.shape == (2, 3) and df.iloc[0, 0] == pytest.approx(-0.015) and df.iloc[1, 2] == pytest.approx(0.03)
    assert np.isnan(df.iloc[0, 2])


def monthly(values, start="2000-01"):
    return pd.Series(values, index=pd.period_range(start, periods=len(values), freq="M"), dtype=float)


def test_diversified_tsm_is_the_hand_average_of_sign_times_next_month_return():
    # asset A rises 1% a month for a year then wobbles; asset B falls 1% a month then wobbles
    a = monthly([0.01] * 12 + [0.02, -0.03, 0.01, 0.02])
    b = monthly([-0.01] * 12 + [0.01, 0.02, -0.02, -0.01])
    panel = pd.DataFrame({"A": a, "B": b})
    out = div.diversified_returns(panel, train_end="2001-01", four=False)
    tsm = out["base"]
    # end of 2001-01: trailing 12-month sum is 0.13 for A (bull, +1) and -0.11 + 0.01... < 0 for B (bear, -1); both apply to 2001-02
    assert tsm.iloc[0] == pytest.approx((1 * -0.03 + (-1) * 0.02) / 2)
    # 2001-02 trailing sums: A 0.10 - 0.01 + ... stays bull, B 0.01+... check by the rule itself for the remaining months
    for ts in tsm.index:
        prev = ts - 1
        sa = a.loc[prev - 11:prev].sum()
        sb = b.loc[prev - 11:prev].sum()
        expect = ((1 if sa > 0 else -1) * a.loc[ts] + (1 if sb > 0 else -1) * b.loc[ts]) / 2
        assert tsm.loc[ts] == pytest.approx(expect)
    assert len(tsm) == 3


def test_diversified_opt_uses_each_assets_own_training_weights():
    # asset A: bull months pay, bear months lose  -> w_bear is negative; asset B is the mirror image so its own bear weight differs
    rng = np.random.default_rng(3)
    a = monthly(rng.normal(0.01, 0.04, 120))
    b = monthly(rng.normal(0.00, 0.05, 120))
    panel = pd.DataFrame({"A": a, "B": b})
    out = div.diversified_returns(panel, train_end="2006-12", four=False)
    wa, wb = out["weights"]["A"], out["weights"]["B"]
    assert max(wa.values()) <= 1.0 and max(wb.values()) <= 1.0 and min(wa.values()) >= -1.0      # weights are scaled so the best regime is at most 1 and floored at -1
    assert set(out["weights"]) == {"A", "B"}
    # the average strategy return equals the mean of the two single-asset strategy returns
    single = [tables.strategy_returns(panel[c], "2006-12", False)["opt"] for c in panel]
    expect = pd.concat(single, axis=1).mean(axis=1)
    pd.testing.assert_series_equal(out["opt"], expect, check_names=False, check_freq=False)


def test_rolling_start_sharpe_matches_a_direct_calculation():
    r = monthly(np.r_[np.full(6, 0.01), np.full(6, -0.01)] + np.tile([0.002, -0.002], 6))
    got = div.rolling_start_sharpe(r, starts=[r.index[0], r.index[3]])
    for st, val in got.items():
        x = r.loc[st:]
        assert val == pytest.approx(x.mean() / x.std(ddof=1) * np.sqrt(12))
    assert list(got.index) == [r.index[0], r.index[3]]
