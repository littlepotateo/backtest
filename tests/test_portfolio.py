"""Known-answer tests for the weighting methods and Black-Litterman."""

import numpy as np
import pandas as pd
import pytest

from backtester import Strategy
from backtester.engine import CostModel, RunConfig, Runner
from backtester.portfolio import View, allocate
from backtester.portfolio import bl
from backtester.portfolio import weights as wt

# Idzorek (2005), "A step-by-step guide to the Black-Litterman model": Tables 1, 2, 5, 6.
ASSETS = ["US Bonds", "Intl Bonds", "US Large Growth", "US Large Value", "US Small Growth",
          "US Small Value", "Intl Dev Equity", "Intl Emerg Equity"]
SIGMA = np.array([
    [0.001005, 0.001328, -0.000579, -0.000675, 0.000121, 0.000128, -0.000445, -0.000437],
    [0.001328, 0.007277, -0.001307, -0.000610, -0.002237, -0.000989, 0.001442, -0.001535],
    [-0.000579, -0.001307, 0.059852, 0.027588, 0.063497, 0.023036, 0.032967, 0.048039],
    [-0.000675, -0.000610, 0.027588, 0.029609, 0.026572, 0.021465, 0.020697, 0.029854],
    [0.000121, -0.002237, 0.063497, 0.026572, 0.102488, 0.042744, 0.039943, 0.065994],
    [0.000128, -0.000989, 0.023036, 0.021465, 0.042744, 0.032056, 0.019881, 0.032235],
    [-0.000445, 0.001442, 0.032967, 0.020697, 0.039943, 0.019881, 0.028355, 0.035064],
    [-0.000437, -0.001535, 0.048039, 0.029854, 0.065994, 0.032235, 0.035064, 0.079958]])
W_MKT = np.array([0.1934, 0.2613, 0.1209, 0.1209, 0.0134, 0.0134, 0.2418, 0.0349])
PI_PAPER = np.array([0.0008, 0.0067, 0.0641, 0.0408, 0.0743, 0.0370, 0.0480, 0.0660])
NEW_RETURNS_PAPER = np.array([0.0007, 0.0050, 0.0650, 0.0432, 0.0759, 0.0394, 0.0493, 0.0684])
NEW_WEIGHTS_PAPER = np.array([0.2988, 0.1559, 0.0935, 0.1482, 0.0104, 0.0165, 0.2781, 0.0349])
DELTA = 3.0652                                   # implied by the paper's equilibrium returns
VIEWS = [View({"Intl Dev Equity": 1}, 0.0525, 0.25),
         View({"Intl Bonds": 1, "US Bonds": -1}, 0.0025, 0.50),
         View({"US Large Growth": 0.9, "US Small Growth": 0.1,
               "US Large Value": -0.9, "US Small Value": -0.1}, 0.02, 0.65)]


def random_cov(n, seed):
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n))
    return a @ a.T / n * 0.04 + np.eye(n) * 0.01


# --- Black-Litterman --------------------------------------------------------------------------

def test_reproduces_idzorek_worked_example():
    pi = bl.implied_returns(SIGMA, W_MKT, DELTA)
    assert pi == pytest.approx(PI_PAPER, abs=5e-5)
    p, q, _ = bl.view_matrices(VIEWS, ASSETS)
    omega = bl.omega_he_litterman(p, SIGMA, 0.025)
    assert np.diag(omega) == pytest.approx([0.000709, 0.000141, 0.000866], abs=1e-6)
    mu, _ = bl.posterior(pi, SIGMA, p, q, omega, 0.025)
    assert mu == pytest.approx(NEW_RETURNS_PAPER, abs=1e-4)
    w = bl.unconstrained_weights(mu, SIGMA, DELTA)
    assert w == pytest.approx(NEW_WEIGHTS_PAPER, abs=2e-4)
    assert w[7] == pytest.approx(W_MKT[7], abs=1e-4)             # asset in no view is unchanged


def test_no_views_returns_the_reference_portfolio():
    pi = bl.implied_returns(SIGMA, W_MKT, DELTA)
    mu, cov_post = bl.posterior(pi, SIGMA, np.zeros((0, 8)), np.array([]), np.zeros((0, 0)), 0.05)
    assert mu == pytest.approx(pi)
    assert bl.unconstrained_weights(mu, SIGMA, DELTA) == pytest.approx(W_MKT / W_MKT.sum() * W_MKT.sum())
    assert bl.unconstrained_weights(mu, cov_post, DELTA) == pytest.approx(W_MKT / 1.05)   # He-Litterman
    res = bl.black_litterman(ASSETS, SIGMA, W_MKT, [], risk_aversion=DELTA, max_weight=None)
    assert res.weights == pytest.approx(W_MKT / W_MKT.sum(), abs=1e-5)


def test_view_confidence_limits():
    pi = bl.implied_returns(SIGMA, W_MKT, DELTA)
    p, q, _ = bl.view_matrices(VIEWS, ASSETS)
    certain = bl.omega_from_confidence(p, SIGMA, 0.05, [1.0, 1.0, 1.0])
    mu, _ = bl.posterior(pi, SIGMA, p, q, certain, 0.05)
    assert p @ mu == pytest.approx(q)                             # certain views hold exactly
    ignored = bl.omega_from_confidence(p, SIGMA, 0.05, [0.0, 0.0, 0.0])
    mu0, _ = bl.posterior(pi, SIGMA, p, q, ignored, 0.05)
    assert mu0 == pytest.approx(pi, abs=1e-6)                     # zero confidence: prior
    half = bl.omega_from_confidence(p, SIGMA, 0.05, [0.5, 0.5, 0.5])
    assert half == pytest.approx(bl.omega_he_litterman(p, SIGMA, 0.05))
    # more confidence moves the posterior further toward the view
    gaps = []
    for c in (0.1, 0.5, 0.9):
        m, _ = bl.posterior(pi, SIGMA, p[:1], q[:1], bl.omega_from_confidence(p[:1], SIGMA, 0.05, [c]), 0.05)
        gaps.append(abs(q[0] - p[0] @ m))
    assert gaps[0] > gaps[1] > gaps[2]


def test_tau_cancels_with_he_litterman_omega_and_forms_agree():
    pi = bl.implied_returns(SIGMA, W_MKT, DELTA)
    p, q, _ = bl.view_matrices(VIEWS, ASSETS)
    results = [bl.posterior(pi, SIGMA, p, q, bl.omega_he_litterman(p, SIGMA, t), t)[0] for t in (0.01, 0.05, 0.5)]
    assert results[0] == pytest.approx(results[1]) and results[1] == pytest.approx(results[2])
    tau, omega = 0.05, bl.omega_he_litterman(p, SIGMA, 0.05)
    ts_inv = np.linalg.inv(tau * SIGMA)
    m = np.linalg.inv(ts_inv + p.T @ np.linalg.inv(omega) @ p)
    textbook = m @ (ts_inv @ pi + p.T @ np.linalg.inv(omega) @ q)
    mu, cov_post = bl.posterior(pi, SIGMA, p, q, omega, tau)
    assert mu == pytest.approx(textbook, abs=1e-10)
    assert cov_post == pytest.approx(SIGMA + m, abs=1e-10)


def test_matches_pyportfolioopt():
    from pypfopt.black_litterman import BlackLittermanModel
    cov = pd.DataFrame(SIGMA, index=ASSETS, columns=ASSETS)
    pi = pd.Series(bl.implied_returns(SIGMA, W_MKT, DELTA), index=ASSETS)
    p, q, conf = bl.view_matrices(VIEWS, ASSETS)
    ref = BlackLittermanModel(cov, pi=pi, P=p, Q=q.reshape(-1, 1), omega="idzorek",
                              view_confidences=conf, tau=0.05, risk_aversion=DELTA)
    ours, _ = bl.posterior(pi.to_numpy(), SIGMA, p, q, bl.omega_from_confidence(p, SIGMA, 0.05, conf), 0.05)
    assert ours == pytest.approx(ref.bl_returns().to_numpy(), abs=1e-10)


def test_views_are_validated_and_constraints_hold():
    with pytest.raises(KeyError):
        bl.view_matrices([View({"Nope": 1}, 0.1)], ASSETS)
    with pytest.raises(ValueError):
        bl.view_matrices([View({"US Bonds": 1}, 0.1, 1.5)], ASSETS)
    res = bl.black_litterman(ASSETS, SIGMA, W_MKT, VIEWS, risk_aversion=DELTA, max_weight=0.25)
    assert res.weights.sum() == pytest.approx(1.0)
    assert (res.weights >= -1e-9).all() and (res.weights <= 0.25 + 1e-6).all()
    assert any("cap" in n for n in res.notes)
    assert bl.implied_risk_aversion(0.06, 0.03) == pytest.approx(2.0)
    assert bl.implied_risk_aversion(0.50, 0.01) == 10.0 and bl.implied_risk_aversion(-0.1, 0.02) == 1.0


# --- baseline methods ---------------------------------------------------------------------------

def test_ledoit_wolf_matches_scikit_learn():
    from sklearn.covariance import LedoitWolf
    rng = np.random.default_rng(1)
    x = rng.multivariate_normal(np.zeros(6), random_cov(6, 2), size=120)
    ref = LedoitWolf().fit(x)
    cov, shrink = wt.ledoit_wolf(x)
    assert shrink == pytest.approx(ref.shrinkage_, rel=1e-9)
    assert cov == pytest.approx(ref.covariance_, rel=1e-9)
    assert 0 <= shrink <= 1


def test_risk_parity_equalises_risk_contributions():
    cov = random_cov(6, 3)
    w = wt.risk_parity(cov)
    assert w.sum() == pytest.approx(1.0) and (w > 0).all()
    assert wt.risk_contributions(w, cov) == pytest.approx(np.full(6, 1 / 6), abs=1e-6)
    two = np.array([[0.04, 0.006], [0.006, 0.09]])
    assert wt.risk_parity(two) == pytest.approx(wt.inverse_volatility(two), abs=1e-6)   # two assets
    assert wt.inverse_volatility(two) == pytest.approx([0.6, 0.4])


def test_min_variance_and_mean_variance_closed_forms():
    cov = random_cov(5, 4)
    ones = np.ones(5)
    exact = np.linalg.solve(cov, ones)
    exact /= exact.sum()
    assert wt.min_variance(cov, long_only=False) == pytest.approx(exact, abs=1e-5)
    w = wt.min_variance(cov, long_only=True, max_weight=0.3)
    assert w.sum() == pytest.approx(1) and (w >= -1e-9).all() and (w <= 0.3 + 1e-6).all()
    for other in (wt.equal_weight(5), wt.inverse_volatility(cov)):
        assert w @ cov @ w <= other @ cov @ other + 1e-9 or (other > 0.3).any()
    # mean-variance with returns implied by a portfolio gives that portfolio back
    target = np.array([0.1, 0.3, 0.2, 0.25, 0.15])
    mu = bl.implied_returns(cov, target, 3.0)
    assert wt.mean_variance(mu, cov, 3.0, long_only=True, max_weight=None) == pytest.approx(target, abs=1e-5)
    with pytest.raises(ValueError):
        wt.min_variance(cov, max_weight=0.1)                      # 5 x 10% cannot reach 100%


# --- allocate() and use inside a strategy ---------------------------------------------------------

def make_returns(n=400, seed=5):
    rng = np.random.default_rng(seed)
    vols = np.array([0.01, 0.02, 0.005, 0.015])
    return pd.DataFrame(rng.normal(0.0003, vols, size=(n, 4)), columns=list("ABCD"))


def test_allocate_methods_sum_to_one_and_fall_back():
    r = make_returns()
    for method in ("equal", "inverse_vol", "risk_parity", "min_variance", "mean_variance", "black_litterman"):
        out = allocate(method, r, max_weight=0.6)
        w = np.array(list(out["weights"].values()))
        assert w.sum() == pytest.approx(1.0), method
        assert (w >= -1e-9).all() and (w <= 0.6 + 1e-6).all(), method
    assert allocate("equal", r)["weights"] == {s: 0.25 for s in "ABCD"}
    iv = allocate("inverse_vol", r)["weights"]
    assert iv["C"] > iv["A"] > iv["D"] > iv["B"]                   # least volatile gets most
    short = allocate("risk_parity", r.iloc[:5])
    assert short["method"] == "inverse_vol" and "Too little history" in short["notes"][0]
    with pytest.raises(ValueError):
        allocate("magic", r)


def test_allocate_black_litterman_prior_and_views():
    r = make_returns()
    ref = {"A": 0.4, "B": 0.1, "C": 0.3, "D": 0.2}
    none = allocate("black_litterman", r, prior_weights=ref, max_weight=None)
    assert none["weights"] == pytest.approx(ref, abs=1e-4)          # no views: reference portfolio
    tilted = allocate("black_litterman", r, prior_weights=ref, max_weight=None,
                      views=[View({"B": 1, "A": -1}, 0.05, 0.8)])
    assert tilted["weights"]["B"] > ref["B"] and tilted["weights"]["A"] < ref["A"]
    assert tilted["posterior_returns"]["B"] > tilted["prior_returns"]["B"]
    no_ref = allocate("black_litterman", r)
    assert any("not a market equilibrium" in n for n in no_ref["notes"])


def test_rebalance_inside_the_engine_uses_only_past_data_and_sells_first(bars):
    rng = np.random.default_rng(6)
    data = {s: bars(100 * np.exp(np.cumsum(rng.normal(0.0004, v, 300))))
            for s, v in (("A", 0.01), ("B", 0.02), ("C", 0.005))}

    class Monthly(Strategy):
        universe = ["A", "B", "C"]
        params = {"method": "risk_parity"}

        def init(self, ctx):
            self.month = None
            self.seen = []

        def on_bar(self, ctx):
            if ctx.now.month == self.month:
                return
            self.month = ctx.now.month
            r = ctx.returns(self.universe, 120)
            self.seen.append((ctx.now, r.index[-1] if len(r) else None))
            if len(r) >= 60:
                out = allocate(self.params["method"], r, max_weight=None)
                ctx.rebalance(out["weights"])
                ctx.record("rebalance", out["weights"])

    runner = Runner(Monthly, RunConfig(costs=CostModel.zero(), fractional_shares=True), data=data)
    res = runner.run()
    strat_seen = res.meta["records"]
    assert len(strat_seen) >= 5 and strat_seen[0]["name"] == "rebalance"
    assert res.gross_exposure.iloc[-1] == pytest.approx(1.0, abs=0.03)       # stays fully invested
    # weights recorded at a rebalance depend only on data up to that date
    cut_time = pd.Timestamp(strat_seen[3]["time"])
    short = Runner(Monthly, RunConfig(costs=CostModel.zero(), fractional_shares=True),
                   data={s: d[d.index <= cut_time] for s, d in data.items()}).run()
    assert short.meta["records"][3]["value"] == pytest.approx(strat_seen[3]["value"])
    # risk parity gives the calmest asset the largest weight
    last = strat_seen[-1]["value"]
    assert last["C"] > last["A"] > last["B"]
