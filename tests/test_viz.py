import numpy as np
import pandas as pd
import pytest

from backtester import viz


def series(n=50, seed=1):
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n)), index=pd.date_range("2020-01-01", periods=n))


def test_equity_and_drawdown_has_both_panels_and_the_dashboard_colours():
    fig = viz.equity_and_drawdown(series(), series(seed=2), names=("OPT", "Buy and hold"))
    assert len(fig.data) == 4 and fig.data[0].name == "OPT" and fig.data[0].line.color == "#2a78d6" and fig.data[2].line.color == "#eb6834"
    assert max(fig.data[1].y) <= 1e-12                                              # a drawdown is never positive
    assert fig.layout.yaxis2.title.text == "Drawdown"


def test_rolling_sharpe_two_lines_and_axis_titles():
    fig = viz.rolling_sharpe(series() / 100, series(seed=3) / 100, names=("OPT", "TSM"))
    assert [t.name for t in fig.data] == ["OPT", "TSM"] and fig.layout.yaxis.title.text == "Annualised Sharpe ratio"


def test_coefficient_panels_one_per_column_with_zero_lines():
    coefs = pd.DataFrame({"r1": series() / 100, "r12": series(seed=4) / 100})
    fig = viz.coefficient_over_time(coefs)
    assert len(fig.data) == 2 and len(fig.layout.shapes) == 2


def test_intraday_profile_thirteen_bars_and_groups():
    one = viz.intraday_profile(pd.Series(np.arange(1.0, 14.0), index=range(1, 14)))
    assert len(one.data) == 1 and len(one.data[0].x) == 13
    two = viz.intraday_profile(pd.DataFrame({"High volatility": np.arange(13.0), "Low volatility": np.arange(13.0)}, index=range(1, 14)))
    assert len(two.data) == 2


def test_regime_weights_bars_per_regime(tmp_path):
    w = pd.DataFrame({"Bull": [1, 1], "Bear": [0.05, -0.01]}, index=["1968-12", "1973-12"])
    fig = viz.regime_weights(w)
    assert [t.name for t in fig.data] == ["Bull", "Bear"]
    out = viz.save(fig, tmp_path / "a" / "weights.html")
    text = out.read_text(encoding="utf-8")
    assert out.exists() and "plotly" in text.lower() and "Bear" in text


def test_dark_mode_changes_the_template():
    assert viz.equity_and_drawdown(series(), dark=True).layout.template.layout.paper_bgcolor != viz.equity_and_drawdown(series()).layout.template.layout.paper_bgcolor


def test_dark_palette_matches_the_dashboard():
    fig = viz.equity_and_drawdown(series(), series(seed=2), dark=True)
    assert fig.data[0].line.color == "#3987e5" and fig.data[2].line.color == "#d95926"


def test_rolling_sharpe_accepts_a_monthly_period_index():
    idx = pd.period_range("1969-01", periods=5, freq="M")
    fig = viz.rolling_sharpe(pd.Series([0.5, 0.6, 0.55, 0.7, 0.65], index=idx), pd.Series([0.4] * 5, index=idx), names=("OPT", "TSM"))
    assert len(fig.data) == 2 and pd.Timestamp(fig.data[0].x[0]) == pd.Timestamp("1969-01-01")
