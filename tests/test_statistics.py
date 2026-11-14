"""Known-answer tests for resampling, Kelly and the overfitting statistics."""

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from backtester.analysis import kelly, overfitting
from backtester.analysis.resample import (bootstrap_paths, optimal_block_length,
                                          stationary_bootstrap_indices)


def ar1(n, phi, seed):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + rng.normal()
    return x


# --- resampling -----------------------------------------------------------------------

def test_stationary_bootstrap_block_lengths_and_range():
    rng = np.random.default_rng(0)
    idx = stationary_bootstrap_indices(1000, 10, rng, size=200_000)
    assert idx.min() >= 0 and idx.max() < 1000
    consecutive = (np.diff(idx) % 1000) == 1
    assert 1 / (1 - consecutive.mean()) == pytest.approx(10, rel=0.05)   # mean block length
    assert len(stationary_bootstrap_indices(50, 5, rng)) == 50
    # block of 1 is an ordinary i.i.d. bootstrap; same seed gives the same indices
    a = stationary_bootstrap_indices(100, 7, np.random.default_rng(3))
    b = stationary_bootstrap_indices(100, 7, np.random.default_rng(3))
    assert (a == b).all()


def test_block_bootstrap_keeps_autocorrelation_and_iid_loses_it():
    x = ar1(4000, 0.6, 1)

    def lag1(v):
        return np.corrcoef(v[:-1], v[1:])[0, 1]

    rng = np.random.default_rng(2)
    blocked = np.mean([lag1(p) for p in bootstrap_paths(x, 50, rng, block=50)])
    iid = np.mean([lag1(p) for p in bootstrap_paths(x, 50, rng, block=1)])
    assert blocked > 0.5 and abs(iid) < 0.05


def test_bootstrap_mean_and_dispersion_for_iid_data():
    rng = np.random.default_rng(4)
    x = rng.normal(0.001, 0.01, 2000)
    means = bootstrap_paths(x, 2000, rng, block=1).mean(axis=1)
    assert means.mean() == pytest.approx(x.mean(), abs=5e-5)
    assert means.std() == pytest.approx(x.std() / math.sqrt(len(x)), rel=0.1)


def test_optimal_block_length_matches_arch_and_grows_with_dependence():
    from arch.bootstrap import optimal_block_length as arch_obl
    for phi, seed in ((0.0, 5), (0.5, 6), (0.9, 7)):
        x = ar1(3000, phi, seed)
        assert optimal_block_length(x) == pytest.approx(float(arch_obl(x)["stationary"].iloc[0]), rel=0.02)
    assert optimal_block_length(ar1(3000, 0.9, 8)) > optimal_block_length(ar1(3000, 0.0, 8))


# --- Kelly ----------------------------------------------------------------------------

def test_kelly_closed_forms():
    assert kelly.kelly_binary(0.6, 1.0) == pytest.approx(0.2)
    assert kelly.kelly_binary(0.5, 2.0) == pytest.approx(0.25)
    assert kelly.kelly_binary(0.4, 1.0) == 0.0
    assert kelly.kelly_continuous(0.08, 0.20 ** 2) == pytest.approx(2.0)
    assert kelly.kelly_continuous(-0.01, 0.04) == 0.0


def test_empirical_kelly_matches_coin_flip_and_is_bounded():
    coin = np.array([1.0] * 60 + [-1.0] * 40)                    # p = 0.6, even payoff
    assert kelly.kelly_empirical(coin) == pytest.approx(0.2, abs=1e-4)
    payoff2 = np.array([2.0] * 50 + [-1.0] * 50)
    assert kelly.kelly_empirical(payoff2) == pytest.approx(0.25, abs=1e-4)
    assert kelly.kelly_empirical(np.array([0.1, -0.2, 0.05, -0.1])) == 0.0   # negative edge
    assert kelly.kelly_empirical(np.array([0.0, 0.0])) == 0.0
    r = np.array([0.05, 0.04, 0.06, -0.5])
    assert kelly.kelly_empirical(r) < 1 / 0.5                    # never bets the worst loss to zero
    assert math.isinf(kelly.kelly_empirical(np.array([0.01, 0.02])))


def test_growth_curve_shape_half_kelly_keeps_three_quarters():
    mu, sigma, f_star = 0.0004, 0.01, 4.0                       # f* = mu / sigma^2

    def g(f):                                                    # continuous-model growth
        return f * mu - f * f * sigma * sigma / 2

    assert g(f_star / 2) == pytest.approx(0.75 * g(f_star))
    assert g(2 * f_star) == pytest.approx(0.0, abs=1e-12)
    rng = np.random.default_rng(9)
    r = rng.normal(mu, sigma, 200_000)
    f_hat = kelly.kelly_empirical(r)
    assert f_hat == pytest.approx(r.mean() / r.var(), rel=0.05)  # near the continuous formula
    assert kelly.growth_rate(r, f_hat) >= kelly.growth_rate(r, f_hat * 1.5)
    assert kelly.growth_rate(r, 150.0) == -math.inf              # a scaled loss beyond 100%


# --- Sharpe-ratio statistics ------------------------------------------------------------

def test_probabilistic_sharpe_known_values():
    rng = np.random.default_rng(10)
    r = rng.normal(0.001, 0.01, 1500)
    sr = r.mean() / r.std(ddof=1)
    assert sr > 0
    assert overfitting.probabilistic_sharpe(r, sr) == pytest.approx(0.5)
    assert overfitting.probabilistic_sharpe(r, 0.0) > 0.5 > overfitting.probabilistic_sharpe(r, 2 * sr)
    # normal returns: denominator is sqrt(1 + SR^2 / 2)
    assert overfitting._sr_denominator(0.1, 0.0, 3.0) == pytest.approx(math.sqrt(1 + 0.1 ** 2 / 2))
    # negative skew and fat tails lower the probability
    assert overfitting._sr_denominator(0.1, -1.0, 8.0) > overfitting._sr_denominator(0.1, 0.0, 3.0)
    assert math.isnan(overfitting.probabilistic_sharpe(np.zeros(10)))


def test_min_track_record_length_round_trip():
    rng = np.random.default_rng(11)
    r = rng.normal(0.001, 0.01, 400)
    n = overfitting.min_track_record_length(r, 0.0, 0.95)
    sr = r.mean() / r.std(ddof=1)
    from scipy.stats import kurtosis, skew
    den = overfitting._sr_denominator(sr, skew(r), kurtosis(r, fisher=False))
    assert norm.cdf(sr * math.sqrt(n - 1) / den) == pytest.approx(0.95)   # exactly at the bar
    assert math.isinf(overfitting.min_track_record_length(-r))


def test_expected_max_sharpe_and_deflation():
    assert overfitting.expected_max_sharpe(100, 1.0) == pytest.approx(2.5306, abs=1e-4)
    assert overfitting.expected_max_sharpe(1, 1.0) == 0.0
    assert overfitting.expected_max_sharpe(1000, 1.0) > overfitting.expected_max_sharpe(100, 1.0)
    assert overfitting.expected_max_sharpe(100, 4.0) == pytest.approx(2 * 2.5306, abs=1e-3)
    rng = np.random.default_rng(12)
    r = rng.normal(0.0006, 0.01, 1000)
    one = overfitting.deflated_sharpe(r, 1, 0.001)
    assert one["probability"] == pytest.approx(overfitting.probabilistic_sharpe(r, 0.0))
    assert overfitting.deflated_sharpe(r, 200, 0.001)["probability"] < one["probability"]


def test_effective_trials_between_one_and_n():
    rng = np.random.default_rng(13)
    base = rng.normal(size=500)
    same = pd.DataFrame({i: base for i in range(8)})
    indep = pd.DataFrame(rng.normal(size=(500, 8)))
    assert overfitting.effective_trials(same) == pytest.approx(1.0)
    assert overfitting.effective_trials(indep) == pytest.approx(8.0, abs=0.5)


# --- Probability of backtest overfitting --------------------------------------------------

def test_pbo_is_half_on_noise_and_near_zero_with_a_real_edge():
    rng = np.random.default_rng(14)
    values = [overfitting.pbo_cscv(pd.DataFrame(rng.normal(0, 0.01, (1000, 20))))["pbo"] for _ in range(20)]
    assert np.mean(values) == pytest.approx(0.5, abs=0.1)
    m = rng.normal(0, 0.01, (1000, 20))
    m[:, 3] += 0.003                                             # one configuration truly better
    res = overfitting.pbo_cscv(pd.DataFrame(m))
    assert res["pbo"] < 0.05 and res["splits"] == 252
    with pytest.raises(ValueError):
        overfitting.pbo_cscv(pd.DataFrame(m[:, :1]))
    with pytest.raises(ValueError):
        overfitting.pbo_cscv(pd.DataFrame(m), n_blocks=7)


# --- SPA ------------------------------------------------------------------------------

def test_spa_noise_versus_real_edge_and_agrees_with_arch():
    from arch.bootstrap import SPA
    rng = np.random.default_rng(15)
    noise = pd.DataFrame(rng.normal(0, 0.01, (800, 15)))
    edge = noise.copy()
    edge[4] += 0.002
    p_noise = overfitting.spa_test(noise, n_boot=1000, seed=1, block=5)
    p_edge = overfitting.spa_test(edge, n_boot=1000, seed=1, block=5)
    assert p_noise["p_value"] > 0.10
    assert p_edge["p_value"] < 0.01 and p_edge["best_configuration"] == 4
    assert p_noise["p_value"] <= p_noise["p_value_reality_check"] + 1e-12
    for m, ours in ((noise, p_noise), (edge, p_edge)):
        ref = SPA(np.zeros(len(m)), -m.to_numpy(), block_size=5, reps=1000, seed=1)
        ref.compute()
        assert ours["p_value"] == pytest.approx(float(ref.pvalues["consistent"]), abs=0.08)
