"""Diversified strategies (paper section 3.4, equation 21) and the rolling-start Sharpe ratios of Figures 1 and 2.

Regimes are detected per asset from its own history, weights are estimated per asset on the training window and held fixed,
and the portfolio return is the plain average across assets (no volatility scaling, as in the paper).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import replicate_tables as rt  # noqa: E402


def diversified_returns(panel: pd.DataFrame, train_end: str, four: bool, compound: bool = False) -> dict:
    """Out-of-sample monthly returns of the equal-weight average of the per-asset strategies.

    `base` is the diversified TSM (two states) or DSM (four states); `opt` is the diversified optimal-regime strategy;
    `weights` holds each asset's regime weights. An asset with no history in the training window is skipped."""
    opt, base, weights = {}, {}, {}
    for col in panel.columns:
        r = panel[col].dropna()
        try:
            x = rt.strategy_returns(r, train_end, four, compound)
        except (ValueError, KeyError):
            continue
        if x["n_train"] == 0 or x["n_test"] == 0:
            continue
        opt[col], base[col], weights[col] = x["opt"], x["base"], x["w_opt"]
    return {"opt": pd.DataFrame(opt).mean(axis=1), "base": pd.DataFrame(base).mean(axis=1), "weights": weights, "n_assets": len(opt)}


def sharpe_of(r: pd.Series) -> float:
    return rt.sharpe(r.dropna())


def rolling_start_sharpe(r: pd.Series, starts) -> pd.Series:
    """Annualised Sharpe ratio of `r` over the window that starts in each month of `starts` and ends at the sample end."""
    return pd.Series({st: rt.sharpe(r.loc[st:]) for st in starts})


def figure_series(mkt: pd.Series, four: bool, train_end: str = "1968-12", first: str = "1969-01", last: str = "2012-12") -> pd.DataFrame:
    """Figures 1 (two states: OPT vs TSM) and 2 (four states: OPT vs DSM): weights are fixed on the training window ending `train_end`;
    for each start month the Sharpe ratio of each strategy is computed from that month to the end of the data."""
    x = rt.strategy_returns(mkt, train_end, four)
    starts = pd.period_range(first, last, freq="M")
    return pd.DataFrame({"OPT": rolling_start_sharpe(x["opt"], starts), "benchmark": rolling_start_sharpe(x["base"], starts)})
