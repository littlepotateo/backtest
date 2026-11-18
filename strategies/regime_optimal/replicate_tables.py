"""Replicates the out-of-sample tables of Zakamulin (2026), "Rethinking Trend Following: Optimal Regime-Dependent Allocation",
with the paper's own method on monthly Kenneth French data (Tables 2, 3 and 5). Run from the project folder:

    .venv/bin/python strategies/regime_optimal/replicate_tables.py

This is the exact-method cross-check for the engine run in `strategy.py` (see spec.md for the assumptions).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).parent))
import french  # noqa: E402

PAPER_T2 = {  # training end -> (TSM, OPT, wBu, wBe, DIF), from Table 2 of the paper
    "1968-12": (0.413, 0.559, 1.00, 0.05), "1973-12": (0.422, 0.597, 1.00, -0.01), "1978-12": (0.477, 0.647, 1.00, 0.00),
    "1983-12": (0.497, 0.666, 1.00, 0.01), "1988-12": (0.567, 0.734, 1.00, 0.05), "1993-12": (0.530, 0.709, 1.00, 0.04),
    "1998-12": (0.459, 0.631, 1.00, 0.05), "2003-12": (0.494, 0.727, 1.00, 0.05)}
PAPER_T3 = {"Large": (0.553, 0.790, 0.13), "Small": (0.074, 0.366, 0.31), "Value": (0.689, 0.856, 0.03), "Growth": (0.092, 0.521, 0.27)}
PAPER_T5 = {  # training end -> (DSM, OPT, wBu, wCo, wBe, wRe)
    "1968-12": (0.504, 0.625, 1.00, 0.61, 0.01, 0.09), "1973-12": (0.520, 0.668, 1.00, 0.50, -0.10, 0.11),
    "1978-12": (0.568, 0.718, 1.00, 0.45, -0.13, 0.17), "1983-12": (0.557, 0.690, 1.00, 0.31, -0.11, 0.19),
    "1988-12": (0.603, 0.714, 1.00, 0.27, -0.08, 0.21), "1993-12": (0.590, 0.763, 1.00, 0.45, -0.11, 0.24),
    "1998-12": (0.495, 0.635, 1.00, 0.38, -0.09, 0.22), "2003-12": (0.507, 0.735, 1.00, 0.41, -0.14, 0.23)}
PAPER_T6 = {"Large": (0.566, 0.756), "Small": (0.329, 0.394), "Value": (0.742, 0.814), "Growth": (0.237, 0.564)}


def regimes(r: pd.Series, four: bool, compound: bool = False) -> pd.Series:
    """Regime observed at the END of each month (it applies to the next month's return). Two-state: 0 = Bear, 1 = Bull.
    The trailing 12-month excess return is the SUM of the 12 monthly excess returns by default: the paper does not say whether
    it is a sum or a compounded return, and the sum reproduces its TSM Sharpe ratios (0.413 and 0.494 are matched to about 0.002).
    Four-state: Bull 1, Correction 2, Bear 3, Rebound 4 (slow = trailing 12-month return, fast = latest month)."""
    slow = (1 + r).rolling(12).apply(np.prod, raw=True) - 1 if compound else r.rolling(12).sum()
    slow_up = slow > 0
    if not four:
        return pd.Series(np.where(slow.isna(), np.nan, np.where(slow_up, 1, 0)), index=r.index)
    fast_up = r > 0
    code = np.select([slow_up & fast_up, slow_up & ~fast_up, ~slow_up & ~fast_up, ~slow_up & fast_up], [1, 2, 3, 4], default=0)
    return pd.Series(np.where(slow.isna(), np.nan, code), index=r.index)


def table(r: pd.Series, four: bool, compound: bool = False) -> pd.DataFrame:
    """Return r_t with the regime that was observed at t-1; first month with a valid regime onward."""
    s = regimes(r, four, compound).shift(1)
    return pd.DataFrame({"r": r, "s": s}).dropna()


def opt_weights(d: pd.DataFrame, states: list[int]) -> dict[int, float]:
    """Equations (16)-(19): score m/q, normalise by the largest, truncate at -1. A state never seen gets weight 0."""
    score = {}
    for s in states:
        x = d.loc[d.s == s, "r"]
        score[s] = (x.mean() / (x ** 2).mean()) if len(x) else 0.0
    c = max(score.values())
    if c <= 0:
        return {s: 0.0 for s in states}                    # no regime has a positive signal-to-noise ratio: stay out
    return {s: max(v / c, -1.0) for s, v in score.items()}


def dsm_weights(d: pd.DataFrame) -> dict[int, float]:
    """Dynamic speed momentum: Bull +1 and Bear -1 are fixed; the Correction weight 1-2a and Rebound weight 2a-1
    (a in [0,1]) are chosen to maximise the in-sample Sharpe ratio."""
    def neg_sharpe(x):
        w = {1: 1.0, 2: x[0], 3: -1.0, 4: x[1]}
        R = d.r * d.s.map(w)
        return -R.mean() / R.std(ddof=1)
    best = None
    for start in ([0, 0], [0.5, -0.5], [-0.5, 0.5], [1, -1]):
        res = minimize(neg_sharpe, start, bounds=[(-1, 1), (-1, 1)], method="L-BFGS-B")
        if best is None or res.fun < best.fun:
            best = res
    return {1: 1.0, 2: float(best.x[0]), 3: -1.0, 4: float(best.x[1])}


def sharpe(R: pd.Series) -> float:
    return float(R.mean() / R.std(ddof=1) * np.sqrt(12))


def strategy_returns(r: pd.Series, train_end: str, four: bool, compound: bool = False) -> dict:
    """Weights estimated on the training window (up to `train_end`), then held fixed: the monthly out-of-sample returns of the
    optimal-regime strategy (`opt`) and of its benchmark (`base`: TSM for two states, DSM for four), with the weights."""
    d = table(r, four, compound)
    train = d[d.index <= pd.Period(train_end, "M")]
    test = d[d.index > pd.Period(train_end, "M")]
    states = [1, 2, 3, 4] if four else [0, 1]
    w_opt = opt_weights(train, states)
    w_base = dsm_weights(train) if four else {1: 1.0, 0: -1.0}
    return {"opt": test.r * test.s.map(w_opt), "base": test.r * test.s.map(w_base), "w_opt": w_opt, "w_base": w_base,
            "n_train": len(train), "n_test": len(test)}


def evaluate(r: pd.Series, train_end: str, four: bool, compound: bool = False, fixed: dict | None = None):
    x = strategy_returns(r, train_end, four, compound)
    return {"opt": sharpe(x["opt"]), "base": sharpe(x["base"]), "w_opt": x["w_opt"], "w_base": x["w_base"],
            "n_train": x["n_train"], "n_test": x["n_test"]}


def main() -> None:
    f = french.factors_monthly()
    mkt = f["Mkt-RF"].dropna()
    print(f"Monthly US market excess return: {mkt.index[0]} to {mkt.index[-1]} ({len(mkt)} months). Source: Kenneth French data library.\n")
    print("TABLE 2 (two-state, total US market). Out-of-sample annualised Sharpe, weights held fixed after the training window.")
    print(f"{'train end':>9} | {'TSM paper':>9} {'TSM here':>9} | {'OPT paper':>9} {'OPT here':>9} | {'wBe paper':>9} {'wBe here':>9}")
    rows2 = []
    for te, (tsm, opt, _, wbe) in PAPER_T2.items():
        e = evaluate(mkt.loc[:"2025-12"], te, False)
        rows2.append((te, tsm, e["base"], opt, e["opt"], wbe, e["w_opt"][0]))
        print(f"{te:>9} | {tsm:9.3f} {e['base']:9.3f} | {opt:9.3f} {e['opt']:9.3f} | {wbe:9.2f} {e['w_opt'][0]:9.2f}")
    print("\nTABLE 5 (four-state, total US market): DSM vs OPT")
    print(f"{'train end':>9} | {'DSM paper':>9} {'DSM here':>9} | {'OPT paper':>9} {'OPT here':>9} | weights paper (Bu,Co,Be,Re) | weights here")
    for te, (dsm, opt, *wp) in PAPER_T5.items():
        e = evaluate(mkt.loc[:"2025-12"], te, True)
        w = e["w_opt"]
        print(f"{te:>9} | {dsm:9.3f} {e['base']:9.3f} | {opt:9.3f} {e['opt']:9.3f} | {tuple(wp)} | ({w[1]:.2f},{w[2]:.2f},{w[3]:.2f},{w[4]:.2f})")
    rf = f["RF"]
    me, bm = french.portfolios_monthly("Portfolios_Formed_on_ME"), french.portfolios_monthly("Portfolios_Formed_on_BE-ME")
    series = {"Large": me["Hi 20"], "Small": me["Lo 20"], "Value": bm["Hi 20"], "Growth": bm["Lo 20"]}
    print("\nTABLE 3 (two-state) and TABLE 6 (four-state), four US portfolios, training 1926-07 to 2003-12, evaluation 2004-01 to 2025-12")
    print(f"{'':>7} | {'TSM p/h':>13} | {'OPT p/h':>13} | {'wBe p/h':>11} | {'DSM p/h':>13} | {'OPT4 p/h':>13}")
    for name, s in series.items():
        r = (s - rf).dropna().loc[:"2025-12"]
        two, four = evaluate(r, "2003-12", False), evaluate(r, "2003-12", True)
        t3, t6 = PAPER_T3[name], PAPER_T6[name]
        print(f"{name:>7} | {t3[0]:5.3f}/{two['base']:6.3f} | {t3[1]:5.3f}/{two['opt']:6.3f} | {t3[2]:5.2f}/{two['w_opt'][0]:5.2f} | "
              f"{t6[0]:5.3f}/{four['base']:6.3f} | {t6[1]:5.3f}/{four['opt']:6.3f}")
    print("\nNOTE on Value/Growth: with French's labels (Value = Hi 20 book-to-market, Growth = Lo 20) the rows come out nearly swapped\n"
          "relative to the paper: its Value row matches our Growth row (0.689/0.684, 0.856/0.851, w 0.03/0.03) and its Growth row matches our Value row (0.092/0.097, 0.521/0.529, 0.27/0.27). Large and Small match to about 0.003.\n"
          "French labels Lo 20 book-to-market as growth, so the paper appears to have swapped the two labels; this was not confirmed with the author.")
    # sensitivity to an assumption the paper does not settle: summing versus compounding the 12 monthly excess returns
    print("\nSENSITIVITY (not in the paper): trailing 12-month return COMPOUNDED instead of summed (the default above)")
    for te in ("1968-12", "2003-12"):
        e = evaluate(mkt.loc[:"2025-12"], te, False, compound=True)
        print(f"  train end {te}: TSM {e['base']:.3f}, OPT {e['opt']:.3f}, w_bear {e['w_opt'][0]:.2f}")


if __name__ == "__main__":
    main()
