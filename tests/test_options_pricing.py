"""Known-answer tests for option pricing and the volatility surface."""

import math

import numpy as np
import pandas as pd
import pytest

from backtester.options import pricing as bs
from backtester.options.surface import SurfaceParams, VolSurface, realised_vol


def test_textbook_values_and_put_call_parity():
    assert bs.price(100, 100, 1, 0.05, 0, 0.2, "C") == pytest.approx(10.4506, abs=1e-4)
    assert bs.price(100, 100, 1, 0.05, 0, 0.2, "P") == pytest.approx(5.5735, abs=1e-4)
    rng = np.random.default_rng(0)
    for _ in range(200):
        s, k = rng.uniform(50, 150, 2)
        t, r, q, v = rng.uniform(0.01, 2), rng.uniform(0, 0.08), rng.uniform(0, 0.04), rng.uniform(0.05, 1)
        parity = s * math.exp(-q * t) - k * math.exp(-r * t)
        assert bs.price(s, k, t, r, q, v, "C") - bs.price(s, k, t, r, q, v, "P") == pytest.approx(parity, abs=1e-10)
    with pytest.raises(ValueError):
        bs.price(100, 100, 1, 0, 0, 0.2, "X")


def test_expiry_gives_intrinsic_value():
    assert bs.price(105, 100, 0, 0.05, 0, 0.2, "C") == 5
    assert bs.price(105, 100, 0, 0.05, 0, 0.2, "P") == 0
    assert bs.price(95, 100, -0.01, 0.05, 0, 0.2, "P") == 5
    g = bs.greeks(105, 100, 0, 0.05, 0, 0.2, "C")
    assert g["delta"] == 1 and g["gamma"] == 0


def test_greeks_match_finite_differences():
    s, k, t, r, q, v = 100.0, 95.0, 0.4, 0.03, 0.015, 0.25
    for right in ("C", "P"):
        g = bs.greeks(s, k, t, r, q, v, right)
        h = 1e-3
        up, dn = bs.price(s + h, k, t, r, q, v, right), bs.price(s - h, k, t, r, q, v, right)
        mid = bs.price(s, k, t, r, q, v, right)
        assert g["delta"] == pytest.approx((up - dn) / (2 * h), abs=1e-6)
        assert g["gamma"] == pytest.approx((up - 2 * mid + dn) / h ** 2, abs=1e-5)
        assert g["vega"] == pytest.approx((bs.price(s, k, t, r, q, v + h, right) - bs.price(s, k, t, r, q, v - h, right)) / (2 * h), rel=1e-5)
        assert g["theta"] == pytest.approx(-(bs.price(s, k, t + h, r, q, v, right) - bs.price(s, k, t - h, r, q, v, right)) / (2 * h), rel=1e-4)
    c, p = bs.greeks(s, k, t, r, q, v, "C"), bs.greeks(s, k, t, r, q, v, "P")
    assert c["delta"] - p["delta"] == pytest.approx(math.exp(-q * t))
    assert c["gamma"] == pytest.approx(p["gamma"])


def test_gamma_peaks_near_the_money_and_grows_toward_expiry():
    strikes = np.arange(60, 141, 1.0)
    g = bs.greeks(100, strikes, 0.25, 0.03, 0, 0.2, "C")["gamma"]
    assert abs(strikes[np.argmax(g)] - 100) <= 3
    atm = [bs.greeks(100, 100, t, 0.03, 0, 0.2, "C")["gamma"] for t in (1.0, 0.25, 0.05, 0.01)]
    assert atm == sorted(atm)
    assert atm[0] == pytest.approx(math.exp(-0.5 * ((0.03 + 0.02) / 0.2) ** 2) / math.sqrt(2 * math.pi) / (100 * 0.2), rel=1e-9)


def test_implied_volatility_round_trip():
    for right, k in (("C", 110), ("P", 90), ("C", 100)):
        p = bs.price(100, k, 0.3, 0.04, 0.01, 0.37, right)
        assert bs.implied_vol(p, 100, k, 0.3, 0.04, 0.01, right) == pytest.approx(0.37, abs=1e-8)
    assert math.isnan(bs.implied_vol(40, 100, 50, 0.5, 0.0, 0, "C"))          # below intrinsic value
    assert math.isnan(bs.implied_vol(60, 100, 50, 0.5, 0.0, 0, "P"))          # above the bound


def make_surface(params=SurfaceParams(), levels=(0.20, 0.30)):
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    return VolSurface(params, pd.Series(levels, index=idx), "test")


def test_surface_level_uses_only_past_values():
    s = make_surface()
    assert s.level_on("2024-01-02") == 0.20
    assert s.level_on("2024-01-03") == 0.30
    assert s.level_on("2024-02-15") == 0.30                       # carries the last known value
    assert s.level_on(pd.Timestamp("2024-01-02 20:00", tz="UTC")) == 0.20
    with pytest.raises(ValueError):
        s.level_on("2023-12-29")


def test_surface_shape_bounds_and_term_structure():
    p = SurfaceParams(ratio=0.9, skew=-0.13, curvature=0.03, term=0.04)
    s = make_surface(p)
    t30 = 30 / 365
    assert s.vol("2024-01-02", t30, 100, 100) == pytest.approx(0.20 * 0.9)      # at the money, 30 days
    strikes = np.array([80, 90, 100, 110, 120.0])
    v = s.vol("2024-01-02", t30, strikes, 100)
    assert v[0] > v[1] > v[2] and v[1] > v[3]                      # puts richer than calls
    assert ((v >= 0.05) & (v <= 3.0)).all()
    ts = np.array([7, 30, 90, 365]) / 365
    atm = np.array([s.vol("2024-01-02", t, 100, 100) for t in ts])
    assert (np.diff(atm ** 2 * ts) > 0).all()                      # total variance never falls with time
    wild = make_surface(SurfaceParams(skew=-5, curvature=0))
    assert (wild.vol("2024-01-02", t30, strikes, 100) >= 0.05).all()
    assert s.vol("2024-01-03", t30, 100, 100) == pytest.approx(0.30 * 0.9)


def test_surface_scaling_and_spread_and_config(tmp_path):
    p = SurfaceParams()
    hi = p.scaled(level=1.1, skew=1.25)
    assert hi.ratio == pytest.approx(p.ratio * 1.1) and hi.skew == pytest.approx(p.skew * 1.25)
    s = make_surface(p)
    assert s.half_spread(10.0) == pytest.approx(0.20) and s.half_spread(0.05) == pytest.approx(0.01)
    cfg = tmp_path / "v.toml"
    cfg.write_text("[SPY]\nratio = 0.85\nskew = -0.2\ncalibrated = true\n")
    loaded = SurfaceParams.load("spy", cfg)
    assert loaded.ratio == 0.85 and loaded.skew == -0.2 and loaded.calibrated
    assert SurfaceParams.load("QQQ", cfg) == SurfaceParams()
    assert SurfaceParams.load("SPY", tmp_path / "missing.toml") == SurfaceParams()


def test_realised_volatility():
    rng = np.random.default_rng(1)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 2000))))
    rv = realised_vol(close, 21)
    assert rv.iloc[:21].isna().all()
    assert rv.dropna().mean() == pytest.approx(0.01 * math.sqrt(252), rel=0.05)
