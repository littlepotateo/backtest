"""Known-answer tests for the Sharpe-optimal regime allocation of Zakamulin (2026), from the paper's own formulas."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

FOLDER = Path(__file__).resolve().parent.parent / "strategies" / "regime_optimal"


def load(name):
    sys.path.insert(0, str(FOLDER))
    spec = importlib.util.spec_from_file_location(f"regime_optimal_{name}", FOLDER / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


strat = load("strategy")
tables = load("replicate_tables")


def series(values, start="2000-01"):
    return pd.Series(values, index=pd.period_range(start, periods=len(values), freq="M"), dtype=float)


def test_the_best_regime_gets_one_and_the_others_scale_by_signal_to_noise():
    # regime 1: m = 0.01, q = 0.001 -> score 10;   regime 0: m = -0.002, q = 0.002 -> score -1   =>   w = (1, -0.1)
    # build returns with exactly these moments: mean a and mean square 0.001; mean -b and mean square 0.002
    a, b = 0.01, 0.002
    x1 = series([a + np.sqrt(0.001 - a * a), a - np.sqrt(0.001 - a * a)] * 2)            # mean a, mean square 0.001
    x0 = series([-b + np.sqrt(0.002 - b * b), -b - np.sqrt(0.002 - b * b)] * 2)            # mean -b, mean square 0.002
    r = pd.concat([x1, x0]).reset_index(drop=True)
    r.index = pd.period_range("2000-01", periods=8, freq="M")
    s = pd.Series([1] * 4 + [0] * 4, index=r.index, dtype=float)
    w = strat.optimal_weights(r, s, [0, 1])
    assert w[1] == pytest.approx(1.0) and w[0] == pytest.approx(-0.1)


def test_weights_are_floored_at_a_full_short():
    # scores 10 and -50 -> -50/10 = -5, truncated to -1
    a, b = 0.01, 0.01
    hi = series([a + np.sqrt(0.001 - a * a), a - np.sqrt(0.001 - a * a)])
    lo = series([-b + np.sqrt(0.0002 - b * b), -b - np.sqrt(0.0002 - b * b)])          # m = -0.01, q = 0.0002 -> score -50
    r = pd.concat([hi, lo]).reset_index(drop=True)
    r.index = pd.period_range("2000-01", periods=4, freq="M")
    s = pd.Series([1, 1, 0, 0], index=r.index, dtype=float)
    assert strat.optimal_weights(r, s, [0, 1]) == {0: pytest.approx(-1.0), 1: pytest.approx(1.0)}


def test_no_positive_score_means_no_investment_and_unseen_regimes_get_zero():
    r = series([-0.01, -0.02, -0.01, -0.03])
    s = pd.Series([1, 1, 0, 0], index=r.index, dtype=float)
    assert strat.optimal_weights(r, s, [0, 1]) == {0: 0.0, 1: 0.0}
    r2 = series([0.02, 0.01, 0.03, 0.02])
    s2 = pd.Series([1, 1, 1, 1], index=r2.index, dtype=float)
    w = strat.optimal_weights(r2, s2, [0, 1])
    assert w[1] == 1.0 and w[0] == 0.0


def test_the_optimal_weights_maximise_the_training_sharpe_ratio_and_beat_tsm():
    rng = np.random.default_rng(3)
    n = 600
    r = pd.Series(rng.normal(0.006, 0.045, n), index=pd.period_range("1950-01", periods=n, freq="M"))
    s = pd.Series(rng.integers(0, 2, n).astype(float), index=r.index)
    r = r + 0.012 * (s - 0.5) * 2 * 0.3                      # give the regimes different means
    w = strat.optimal_weights(r, s, [0, 1])

    def sharpe(wb):
        R = r * s.map({1: 1.0, 0: wb})
        return R.mean() / R.std(ddof=1)
    best_bear = max(np.linspace(-1, 1, 801), key=sharpe)
    assert sharpe(w[0]) >= sharpe(best_bear) - 1e-3
    assert sharpe(w[0]) > sharpe(-1.0)                       # the canonical -1 is worse here


def test_the_strategy_and_the_cross_check_script_agree():
    rng = np.random.default_rng(5)
    r = pd.Series(rng.normal(0.007, 0.04, 400), index=pd.period_range("1960-01", periods=400, freq="M"))
    for four in (False, True):
        s = strat.regime_codes(r, four).shift(1)
        d = pd.DataFrame({"r": r, "s": s}).dropna()
        states = [1, 2, 3, 4] if four else [0, 1]
        mine = strat.optimal_weights(d.r, d.s, states)
        theirs = tables.opt_weights(tables.table(r, four), states)
        assert mine == pytest.approx(theirs)
        if four:
            assert strat.dsm_weights(d.r, d.s) == pytest.approx(tables.dsm_weights(d), abs=1e-4)


def test_regimes_follow_the_signs_of_the_slow_and_fast_signals():
    r = series([0.01] * 12 + [-0.002, 0.03, -0.07, -0.0005, -0.0005, 0.001, 0.0])
    two = strat.regime_codes(r, False)
    four = strat.regime_codes(r, True)
    assert two.iloc[:11].isna().all() and two.iloc[11] == 1
    # month 12 (index 12): trailing sum 0.118 > 0 and latest -0.002 < 0 -> Correction
    assert four.iloc[12] == strat.CORRECTION
    assert four.iloc[13] == strat.BULL                      # up trend, up month
    assert four.iloc[14] == strat.CORRECTION                # sum still positive (0.01*10 - 0.002 + 0.03 - 0.07 = 0.058)
    assert four.iloc[15] == strat.CORRECTION or four.iloc[15] == strat.BEAR


def test_the_sum_of_twelve_returns_is_the_slow_signal_not_the_compounded_return():
    # twelve months of +10% then -?: the sum and the compounded return can have different signs
    r = series([0.30, -0.25, 0.30, -0.25, 0.30, -0.25, 0.30, -0.25, 0.30, -0.25, 0.30, -0.25])
    assert r.sum() > 0 and ((1 + r).prod() - 1) < 0
    assert strat.regime_codes(r, False).iloc[-1] == 1


def test_the_known_answer_sharpe_identity_of_proposition_1():
    # SR(w*)^2 = kappa/(1-kappa) with kappa = sum_s p_s m_s^2 / q_s
    rng = np.random.default_rng(11)
    n = 20000
    s = pd.Series(rng.integers(0, 3, n).astype(float), index=pd.period_range("1000-01", periods=n, freq="M"))
    means = s.map({0: 0.004, 1: -0.002, 2: 0.0005})
    r = means + pd.Series(rng.normal(0, 0.04, n), index=s.index)
    states = [0, 1, 2]
    m = {k: r[s == k].mean() for k in states}
    q = {k: (r[s == k] ** 2).mean() for k in states}
    p = {k: (s == k).mean() for k in states}
    kappa = sum(p[k] * m[k] ** 2 / q[k] for k in states)
    w = {k: m[k] / q[k] for k in states}                               # unconstrained optimum, any positive scale
    R = r * s.map(w)
    assert (R.mean() / R.std(ddof=1)) ** 2 == pytest.approx(kappa / (1 - kappa), rel=2e-3)
