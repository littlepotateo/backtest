"""Signals, predictive regressions (Newey-West, recursive out-of-sample) and sizing of the intraday momentum study."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

FOLDER = Path(__file__).resolve().parent.parent / "strategies" / "intraday_momentum"


def load(name):
    sys.path.insert(0, str(FOLDER))
    spec = importlib.util.spec_from_file_location(f"intraday_{name}", FOLDER / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


signals, predict, sizing = load("signals"), load("predict"), load("sizing")


def days(n, start="1998-01-02"):
    return pd.bdate_range(start, periods=n).date


# ---- signals (equations 4 and 5) ----------------------------------------------------------------------------------------
def test_timing_signal_with_the_first_half_hour_only():
    r1 = pd.Series([0.01, -0.02, 0.0, 0.003])
    assert signals.timing_signal(r1).tolist() == [1, -1, -1, 1]                  # "short otherwise": zero counts as not positive


def test_timing_signal_with_both_returns_stays_out_when_they_disagree():
    r1 = pd.Series([0.01, -0.01, 0.01, -0.01, 0.0])
    r12 = pd.Series([0.02, -0.02, -0.02, 0.02, 0.0])
    assert signals.timing_signal(r1, r12).tolist() == [1, -1, 0, 0, -1]          # both <= 0 -> short; one of each -> flat


def test_strategy_return_is_signal_times_the_last_half_hour():
    r1, r13 = pd.Series([0.01, -0.01, 0.01]), pd.Series([0.002, 0.001, -0.004])
    assert signals.strategy_returns(signals.timing_signal(r1), r13).tolist() == pytest.approx([0.002, -0.001, -0.004])


def test_summary_statistics_follow_the_paper_conventions():
    r = pd.Series([0.001, -0.0005, 0.002, 0.0, -0.001, 0.0015])
    s = signals.summarize(r)
    assert s["mean_pct"] == pytest.approx(r.mean() * 252 * 100)                  # annualised by 252, in percent
    assert s["sd_pct"] == pytest.approx(r.std(ddof=1) * np.sqrt(252) * 100)
    assert s["sharpe"] == pytest.approx(r.mean() / r.std(ddof=1) * np.sqrt(252))  # no risk-free subtracted (6.67 / 6.19 = 1.08)
    assert s["success_pct"] == pytest.approx(4 / 6 * 100)                        # zero or positive days count as successes
    assert s["kurtosis"] == pytest.approx(pd.Series(r).kurt() + 3)                # raw (not excess) kurtosis, as the paper's 15.65


# ---- regression ------------------------------------------------------------------------------------------------------------
def exact_data():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    y = np.array([1.1, 1.9, 3.2, 3.8, 5.3, 5.9, 7.1, 8.2])
    return pd.Series(y), pd.DataFrame({"x": x})


def test_ols_matches_the_closed_form():
    y, X = exact_data()
    res = predict.predictive_regression(y, X, lags=0)
    x = X["x"].to_numpy()
    slope = ((x - x.mean()) * (y.to_numpy() - y.mean())).sum() / ((x - x.mean()) ** 2).sum()
    assert res["coef"]["x"] == pytest.approx(slope) and res["coef"]["const"] == pytest.approx(y.mean() - slope * x.mean())
    assert res["r2"] == pytest.approx(np.corrcoef(x, y.to_numpy())[0, 1] ** 2)


def newey_west_reference(y, X, lags):
    """Textbook Newey-West (1987): Bartlett weights, sandwich with the long-run covariance of x_t e_t."""
    Z = np.column_stack([np.ones(len(y)), X])
    beta = np.linalg.solve(Z.T @ Z, Z.T @ y)
    e = y - Z @ beta
    n = len(y)
    g = Z * e[:, None]
    S = g.T @ g
    for l in range(1, lags + 1):
        G = g[l:].T @ g[:-l]
        S += (1 - l / (lags + 1)) * (G + G.T)
    bread = np.linalg.inv(Z.T @ Z)
    cov = bread @ S @ bread
    return beta / np.sqrt(np.diag(cov))


@pytest.mark.parametrize("lags", [0, 1, 3])
def test_newey_west_t_statistics_match_the_textbook_formula(lags):
    y, X = exact_data()
    res = predict.predictive_regression(y, X, lags=lags)
    ref = newey_west_reference(y.to_numpy(), X.to_numpy(), lags)
    assert [res["t"]["const"], res["t"]["x"]] == pytest.approx(list(ref))


def test_default_lag_rule_is_written_down():
    assert predict.default_lags(2500) == int(np.floor(4 * (2500 / 100) ** (2 / 9)))


def test_table_scaling_follows_the_paper():
    y, X = exact_data()
    res = predict.predictive_regression(y, X, lags=0)
    scaled = predict.scale_like_table1(res)
    assert scaled["const"] == pytest.approx(res["coef"]["const"] * 252 * 100)
    assert scaled["x"] == pytest.approx(res["coef"]["x"] * 100)
    assert scaled["r2_pct"] == pytest.approx(res["r2"] * 100)


# ---- recursive out-of-sample forecasts (equation 3) -------------------------------------------------------------------------
def planted(n=900, beta=0.08, seed=1):
    rng = np.random.default_rng(seed)
    idx = days(n)
    r1 = pd.Series(rng.normal(0, 0.006, n), index=idx)
    r13 = pd.Series(beta * r1.to_numpy() + rng.normal(0, 0.003, n), index=idx)
    return r13, pd.DataFrame({"r1": r1})


def test_recursive_forecast_uses_only_earlier_months():
    y, X = planted()
    start = pd.Timestamp("1999-01-01").date()
    base = predict.recursive_forecast(y, X, start)
    y2, X2 = y.copy(), X.copy()
    cut = base.index[300]
    y2[y2.index >= cut] += 0.05                                                   # change the future from `cut` on
    X2[X2.index >= cut] *= -3
    changed = predict.recursive_forecast(y2, X2, start)
    before = base.index[base.index < cut]
    pd.testing.assert_frame_equal(base.loc[before, ["rhat", "rbar", "sigma2"]], changed.loc[before, ["rhat", "rbar", "sigma2"]])


def test_coefficients_change_only_at_month_starts():
    y, X = planted()
    f = predict.recursive_forecast(y, X, pd.Timestamp("1999-01-01").date())
    months = pd.Series([d.month + 12 * d.year for d in f.index], index=f.index)
    assert f.groupby(months)["beta_r1"].nunique().max() == 1
    assert f["beta_r1"].nunique() > 5                                              # and they do change from month to month


def test_r2_oos_is_zero_for_the_historical_mean_and_positive_for_a_real_relation():
    y, X = planted()
    f = predict.recursive_forecast(y, X, pd.Timestamp("1999-01-01").date())
    assert predict.r2_oos(y.loc[f.index], f["rbar"], f["rbar"]) == pytest.approx(0.0)
    assert predict.r2_oos(y.loc[f.index], f["rhat"], f["rbar"]) > 0.02            # beta*r1 explains a few percent of the variance
    noise_y, noise_X = planted(beta=0.0, seed=2)
    g = predict.recursive_forecast(noise_y, noise_X, pd.Timestamp("1999-01-01").date())
    assert predict.r2_oos(noise_y.loc[g.index], g["rhat"], g["rbar"]) < 0.005     # nothing to find


def test_forecast_needs_enough_history():
    y, X = planted(n=30)
    with pytest.raises(ValueError):
        predict.recursive_forecast(y, X, pd.Timestamp("1998-01-20").date())


# ---- sizing (equations 6-8) ------------------------------------------------------------------------------------------------
def test_mean_variance_weight_and_its_limits():
    # (1/gamma) * rhat / sigma2 with gamma = 5: 1e-5 / (5 * 1e-5) = 0.2; the large forecasts hit the bounds 1.5 and -0.5
    w = sizing.mean_variance_weight(pd.Series([1e-5, -1e-5, 0.01, -0.01]), pd.Series([1e-5] * 4), gamma=5)
    assert w.tolist() == pytest.approx([0.2, -0.2, 1.5, -0.5])
    assert sizing.mean_variance_weight(pd.Series([1e-5]), pd.Series([4e-5]), gamma=5, lo=-1, hi=2).iloc[0] == pytest.approx(0.05)


def test_utility_and_certainty_equivalent():
    r2 = pd.Series([0.002, -0.001, 0.003, 0.001])
    r1 = pd.Series([0.0005, 0.0004, 0.0006, 0.0005])
    u = lambda r: r.mean() * 252 - 5 / 2 * r.var(ddof=1) * 252
    assert sizing.utility(r2, 5) == pytest.approx(u(r2))
    assert sizing.certainty_equivalent(r2, r1, 5) == pytest.approx(u(r2) - u(r1))


def test_portfolio_return_puts_the_rest_in_the_risk_free_asset():
    r13 = pd.Series([0.01, -0.02]); w = pd.Series([1.5, -0.5]); rf = pd.Series([0.0001, 0.0001])
    assert sizing.portfolio_returns(w, r13, rf).tolist() == pytest.approx([1.5 * 0.01 + (1 - 1.5) * 0.0001, -0.5 * -0.02 + 1.5 * 0.0001])
