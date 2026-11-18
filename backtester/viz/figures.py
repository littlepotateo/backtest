"""Figures for replications. Every function takes plain pandas objects and returns a `plotly.graph_objects.Figure`; `save` writes a
standalone HTML file (no network needed: the Plotly script is embedded). Colours follow the dashboard: the strategy is always series 1
(blue), the benchmark or second series is series 2 (orange)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# the dashboard palette (backtester/web/static/style.css): series 1 blue, series 2 orange, light and dark variants
PALETTE = {False: ("#2a78d6", "#eb6834"), True: ("#3987e5", "#d95926")}
GREY = "#8a8a85"
BLUE, ORANGE = PALETTE[False]


def _layout(fig: go.Figure, title: str, dark: bool) -> go.Figure:
    fig.update_layout(title=title, template="plotly_dark" if dark else "plotly_white", legend=dict(orientation="h", y=1.08),
                      margin=dict(l=60, r=30, t=80, b=50), hovermode="x unified")
    return fig


def _x(s: pd.Series):
    idx = s.index.to_timestamp() if isinstance(s.index, pd.PeriodIndex) else s.index
    return [pd.Timestamp(i) if not isinstance(i, (int, np.integer)) else i for i in idx]


def equity_and_drawdown(equity: pd.Series, benchmark: pd.Series | None = None, title: str = "Equity and drawdown",
                        names: tuple[str, str] = ("Strategy", "Benchmark"), dark: bool = False) -> go.Figure:
    """Equity (rebased to 1) above, drawdown below; an optional benchmark is drawn in series 2."""
    blue, orange = PALETTE[dark]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.06)
    for series, name, color in ((equity, names[0], blue), (benchmark, names[1], orange)):
        if series is None:
            continue
        s = series / series.iloc[0]
        fig.add_trace(go.Scatter(x=_x(s), y=s.to_numpy(), name=name, line=dict(color=color, width=2)), row=1, col=1)
        dd = s / s.cummax() - 1
        fig.add_trace(go.Scatter(x=_x(dd), y=dd.to_numpy(), name=f"{name} drawdown", line=dict(color=color, width=1.5), showlegend=False), row=2, col=1)
    fig.update_yaxes(title_text="Growth of 1", row=1, col=1)
    fig.update_yaxes(title_text="Drawdown", tickformat=".0%", row=2, col=1)
    return _layout(fig, title, dark)


def rolling_sharpe(a: pd.Series, b: pd.Series | None = None, names: tuple[str, str] = ("Strategy", "Benchmark"),
                   title: str = "Sharpe ratio by start date", xaxis_title: str = "Start date", dark: bool = False) -> go.Figure:
    """Two Sharpe-ratio series against a date axis (the paper's Figures 1 and 2: the out-of-sample Sharpe ratio of each strategy computed
    over the window that starts in each month and ends at the sample end)."""
    blue, orange = PALETTE[dark]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=_x(a), y=a.to_numpy(), name=names[0], line=dict(color=blue, width=2)))
    if b is not None:
        fig.add_trace(go.Scatter(x=_x(b), y=b.to_numpy(), name=names[1], line=dict(color=orange, width=2)))
    fig.update_xaxes(title_text=xaxis_title)
    fig.update_yaxes(title_text="Annualised Sharpe ratio")
    return _layout(fig, title, dark)


def coefficient_over_time(coefs: pd.DataFrame, title: str = "Recursive regression coefficients", dark: bool = False) -> go.Figure:
    """One panel per column of `coefs` (the paper's Figure 1: the recursively estimated slopes of r1 and r12), with a zero line."""
    n = coefs.shape[1]
    fig = make_subplots(rows=n, cols=1, shared_xaxes=True, vertical_spacing=0.08, subplot_titles=[str(c) for c in coefs.columns])
    for i, col in enumerate(coefs.columns, start=1):
        fig.add_trace(go.Scatter(x=_x(coefs[col]), y=coefs[col].to_numpy(), name=str(col), line=dict(color=PALETTE[dark][0], width=2), showlegend=False), row=i, col=1)
        fig.add_hline(y=0, line=dict(color=GREY, width=1), row=i, col=1)
    return _layout(fig, title, dark)


def intraday_profile(profile: pd.Series | pd.DataFrame, title: str = "Average volume by half-hour", ytitle: str = "Volume", dark: bool = False) -> go.Figure:
    """Bars for the 13 half-hours (the paper's Figure 2). A DataFrame draws one bar group per column (for example high and low volatility days)."""
    frame = profile.to_frame("All days") if isinstance(profile, pd.Series) else profile
    fig = go.Figure()
    for color, col in zip((*PALETTE[dark], GREY), frame.columns):
        fig.add_trace(go.Bar(x=[int(i) for i in frame.index], y=frame[col].to_numpy(), name=str(col), marker_color=color))
    fig.update_xaxes(title_text="Half-hour of the trading day (1 = 09:30-10:00, 13 = 15:30-16:00)", dtick=1)
    fig.update_yaxes(title_text=ytitle)
    fig.update_layout(barmode="group")
    return _layout(fig, title, dark)


def regime_weights(weights: pd.DataFrame, title: str = "Regime weights", dark: bool = False) -> go.Figure:
    """Grouped bars: one group per row (for example a training window), one bar per column (a regime), with a line at zero."""
    fig = go.Figure()
    palette = (*PALETTE[dark], GREY, "#2f9e6e")
    for color, col in zip(palette, weights.columns):
        fig.add_trace(go.Bar(x=[str(i) for i in weights.index], y=weights[col].to_numpy(), name=str(col), marker_color=color))
    fig.add_hline(y=0, line=dict(color=GREY, width=1))
    fig.update_yaxes(title_text="Weight in the risky asset")
    fig.update_layout(barmode="group")
    return _layout(fig, title, dark)


def save(fig: go.Figure, path: str | Path) -> Path:
    """Write a standalone HTML file (Plotly script embedded, opens offline)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(path), include_plotlyjs=True, full_html=True)
    return path
