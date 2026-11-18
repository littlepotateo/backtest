"""Exact-method reproduction of the core tables of Gao, Han, Li and Zhou (2017), "Market Intraday Momentum" (Tables 1, 2, 6, 7, 10),
on whatever half-hour data it is given. Run from the project folder:

    .venv/bin/python strategies/intraday_momentum/replicate_tables.py --symbol SPY            # the cached SPY 30-minute bars
    .venv/bin/python strategies/intraday_momentum/replicate_tables.py --file spy_1min.csv     # a vendor file (time,open,high,low,close,volume)

The paper's sample is SPY ticks from TAQ, 1993-02-01 to 2013-12-31. Which sample is used here is printed first; on a different or shorter sample
the numbers are NOT comparable with the paper's, and the paper's values are printed beside ours only for orientation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import halfhours  # noqa: E402
import predict  # noqa: E402
import signals  # noqa: E402
import sizing  # noqa: E402

PAPER = {
    "table1_in_sample": {"r1": (6.94, 4.08, 1.6), "r12": (11.8, 2.62, 1.1), "both": ((6.81, 4.14), (11.4, 2.60), 2.6)},
    "table1_oos_r2": {"r1": 1.4, "r12": 0.9, "both": 2.0},
    "table6": {"eta_r1": {"mean": 6.67, "sd": 6.19, "sharpe": 1.08, "skew": 0.90, "kurtosis": 15.65, "success": 54.37},
               "eta_r1_r12": {"mean": 4.39, "success": 77.05}, "eta_r12": {"mean": 1.77, "sharpe": 0.29, "skew": 0.38, "kurtosis": 15.73, "success": 50.93},
               "always_long": {"mean": -1.11, "sd": 6.21, "sharpe": -0.18, "skew": -0.46, "success": 50.42},
               "buy_hold": {"mean": 6.04, "sd": 20.57, "sharpe": 0.29, "skew": -0.16}},
    "table7": {"r1": {"mean": 6.51, "sd": 5.62, "sharpe": 1.16, "cer": 6.02, "hist_mean": 0.46, "hist_sharpe": 0.15},
               "both": {"mean": 6.68, "sharpe": 1.07, "cer": 6.18}},
    "table10": {"after_decimalisation": {"eta_r1_net": 4.46, "eta_r1_gross": 6.93}, "from_2005": {"eta_r1_net": 6.52, "eta_r1_gross": 7.96}},
}
CRISIS = ("2007-12-03", "2009-06-30")
OOS_START = "1998-01-01"


def load_returns(symbol: str | None = None, file: str | None = None, interval: str = "30m", label: str = "start"):
    """Half-hour prices and returns from the cache (`symbol`) or from a CSV or IBKR JSON file."""
    from backtester.data.cache import Cache, from_csv
    from backtester.data.ibkr import parse_ibkr_history
    if file:
        bars = parse_ibkr_history(Path(file))[0] if str(file).endswith(".json") else from_csv(file)
    else:
        bars = Cache().load(symbol or "SPY", interval)
    p = halfhours.to_halfhours(bars, label=label)
    return p, halfhours.returns(p)


def _window(r: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    idx = pd.Series(r.index, index=r.index)
    keep = pd.Series(True, index=r.index)
    if start:
        keep &= idx >= pd.Timestamp(start).date()
    if end:
        keep &= idx <= pd.Timestamp(end).date()
    return r[keep]


def table1(r: pd.DataFrame, oos_start: str = OOS_START) -> dict:
    """Predictive regressions of r13 on r1, r12 and both: in sample (coefficients scaled as in the paper, Newey-West t, R2 %) and the
    recursive out-of-sample R2 % (needs history before `oos_start`)."""
    out = {}
    for name, cols in (("r1", ["r1"]), ("r12", ["r12"]), ("both", ["r1", "r12"])):
        d = r[["r13", *cols]].dropna()
        row = {"n": len(d)}
        if len(d) > len(cols) + 3:
            res = predict.predictive_regression(d["r13"], d[cols])
            scaled = predict.scale_like_table1(res)
            row.update({c: (scaled[c], res["t"][c]) for c in ["const", *cols]})
            row["r2_pct"] = scaled["r2_pct"]
        try:
            f = predict.recursive_forecast(d["r13"], d[cols], pd.Timestamp(oos_start).date())
            row["r2_oos_pct"] = predict.r2_oos(f["y"], f["rhat"], f["rbar"]) * 100
            row["oos_days"] = len(f)
        except ValueError as e:
            row["r2_oos_pct"], row["oos_note"] = float("nan"), str(e)
        out[name] = row
    return out


def table2(r: pd.DataFrame) -> dict:
    """In-sample regressions in the financial-crisis window and the periods around it (Dec 3 2007 - Jun 30 2009)."""
    parts = {"crisis": _window(r, *CRISIS),
             "excluding crisis": pd.concat([_window(r, None, pd.Timestamp(CRISIS[0]) - pd.Timedelta(days=1)), _window(r, pd.Timestamp(CRISIS[1]) + pd.Timedelta(days=1))]),
             "before crisis": _window(r, None, pd.Timestamp(CRISIS[0]) - pd.Timedelta(days=1)),
             "after crisis": _window(r, pd.Timestamp(CRISIS[1]) + pd.Timedelta(days=1))}
    out = {}
    for label, part in parts.items():
        row = {"n": len(part.dropna(subset=["r1", "r12", "r13"]))}
        for name, cols in (("r1", ["r1"]), ("r12", ["r12"]), ("both", ["r1", "r12"])):
            d = part[["r13", *cols]].dropna()
            if len(d) > 10:
                row[name] = predict.scale_like_table1(predict.predictive_regression(d["r13"], d[cols]))["r2_pct"]
        out[label] = row
    return out


def table6(p: pd.DataFrame, r: pd.DataFrame) -> dict:
    """The three timing strategies of equations (4)-(5) with Always Long and Buy-and-Hold, with the paper's summary statistics."""
    d = r[["r1", "r12", "r13"]].dropna()
    out = {"eta_r1": signals.summarize(signals.strategy_returns(signals.timing_signal(d["r1"]), d["r13"])),
           "eta_r12": signals.summarize(signals.strategy_returns(signals.timing_signal(d["r12"]), d["r13"])),
           "eta_r1_r12": signals.summarize(signals.strategy_returns(signals.timing_signal(d["r1"], d["r12"]), d["r13"])),
           "always_long": signals.summarize(d["r13"]),
           "buy_hold": signals.summarize(p["p13"].pct_change().dropna())}
    return out


def table7(r: pd.DataFrame, gamma: float = 5.0, oos_start: str = OOS_START) -> dict:
    """The mean-variance investor of equations (6)-(8): weight on the market in the last half-hour from the recursive forecast, bounded to
    [-0.5, 1.5]; the benchmark uses the historical-average forecast; CER = U2 - U1. The variance forecast is the residual variance of the
    training regression (the paper does not say how it is estimated)."""
    out = {}
    for name, cols in (("r1", ["r1"]), ("both", ["r1", "r12"])):
        d = r[["r13", *cols]].dropna()
        try:
            f = predict.recursive_forecast(d["r13"], d[cols], pd.Timestamp(oos_start).date())
        except ValueError as e:
            out[name] = {"note": str(e)}
            continue
        w = sizing.mean_variance_weight(f["rhat"], f["sigma2"], gamma)
        wbar = sizing.mean_variance_weight(f["rbar"], f["sigma2"], gamma)
        rp, rb = sizing.portfolio_returns(w, f["y"]), sizing.portfolio_returns(wbar, f["y"])
        s, sb = signals.summarize(rp), signals.summarize(rb)
        out[name] = {"mean_pct": s["mean_pct"], "sd_pct": s["sd_pct"], "sharpe": s["sharpe"], "skew": s["skew"],
                     "hist_mean_pct": sb["mean_pct"], "hist_sharpe": sb["sharpe"], "cer_pct": sizing.certainty_equivalent(rp, rb, gamma) * 100,
                     "days": len(f)}
    return out


def trade_cost_fraction(side: int, price: float, half_spread: float, costs) -> float:
    """Cost of one round trip (enter at 15:30, close at the 16:00 auction) as a fraction of the position value: the half-spread at entry
    (the close auction pays none, as in the paper), the SEC and FINRA fees on the SALE leg, and the per-share fees on both legs.
    `costs` is a CostModel (config/costs.toml)."""
    sale = price                                   # value sold: the close (long) or the entry (short), both about `price`
    fee = costs.regulatory_fee(-1.0, sale) + costs.regulatory_fee(+1.0, sale)
    return half_spread + fee / price


def table10(r: pd.DataFrame, half_spread_bps: float, costs, price: pd.Series) -> dict:
    """Net-of-cost strategy returns for eta(r1) and eta(r1, r12). `price` is the 15:30 price (p12) used to turn per-share fees into fractions.
    The spread is `half_spread_bps` basis points of price at entry; the paper's own figure (about 1.2 bp from 2005) is a full spread."""
    d = r[["r1", "r12", "r13"]].dropna()
    px = price.reindex(d.index)
    out = {}
    for name, sig in (("eta_r1", signals.timing_signal(d["r1"])), ("eta_r1_r12", signals.timing_signal(d["r1"], d["r12"]))):
        gross = signals.strategy_returns(sig, d["r13"])
        cost = pd.Series([trade_cost_fraction(int(s), float(pr), half_spread_bps / 1e4, costs) if s else 0.0 for s, pr in zip(sig, px)], index=d.index)
        out[name] = {"gross_mean_pct": signals.summarize(gross)["mean_pct"], "net_mean_pct": signals.summarize(gross - cost)["mean_pct"],
                     "cost_pct_per_year": float(cost.mean() * 252 * 100)}
    return out


def _fmt(x, nd=2):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def report(p: pd.DataFrame, r: pd.DataFrame, costs, half_spread_bps: float, oos_start: str = OOS_START) -> str:
    L = [f"Sample: {p.index[0]} to {p.index[-1]}, {len(p)} complete trading days ({len(r['r13'].dropna())} with r13; {len(p.attrs.get('dropped', {}))} days dropped).",
         "The paper's sample is SPY ticks from TAQ, 1993-02-01 to 2013-12-31 (about 5,200 days). Numbers below are comparable with the paper only on that sample.", ""]
    t1 = table1(r, oos_start)
    L.append("TABLE 1 predictive regression of r13 (slopes x100, intercept x252x100, Newey-West t in brackets)   [paper: r1 6.94 (4.08) R2 1.6; r12 11.8 (2.62) 1.1; both 2.6; OOS R2 1.4 / 0.9 / 2.0]")
    for k, row in t1.items():
        coefs = "  ".join(f"{c}={_fmt(v[0])} ({_fmt(v[1])})" for c, v in row.items() if isinstance(v, tuple))
        L.append(f"  {k:>5}: n={row['n']}  {coefs}  R2={_fmt(row.get('r2_pct'))}%  OOS R2={_fmt(row.get('r2_oos_pct'))}%" + (f"  [{row['oos_note']}]" if "oos_note" in row else ""))
    t2 = table2(r)
    L.append("\nTABLE 2 R2 % by period   [paper: crisis 4.1 / 3.1 / 6.9 (r1, r12, both); excluding crisis 0.8 / 0.3 / 1.1]")
    for k, row in t2.items():
        L.append(f"  {k:>17}: n={row['n']}  r1={_fmt(row.get('r1'))}  r12={_fmt(row.get('r12'))}  both={_fmt(row.get('both'))}")
    t6 = table6(p, r)
    L.append("\nTABLE 6 strategies (annualised, percent)   [paper eta(r1): mean 6.67 sd 6.19 Sharpe 1.08 skew 0.90 kurt 15.65 success 54.37; both signals mean 4.39 success 77.05; Always Long -1.11; Buy-and-Hold 6.04 / 20.57 / 0.29]")
    for k, s in t6.items():
        L.append(f"  {k:>11}: mean={_fmt(s['mean_pct'])}  sd={_fmt(s['sd_pct'])}  Sharpe={_fmt(s['sharpe'])}  skew={_fmt(s['skew'])}  kurt={_fmt(s['kurtosis'])}  success={_fmt(s['success_pct'])}%  (n={s['n']})")
    t7 = table7(r, oos_start=oos_start)
    L.append("\nTABLE 7 mean-variance investor, gamma 5, weight in [-0.5, 1.5]   [paper r1: mean 6.51 sd 5.62 Sharpe 1.16 CER 6.02; both: mean 6.68 Sharpe 1.07 CER 6.18]")
    for k, s in t7.items():
        L.append(f"  {k:>5}: " + (s["note"] if "note" in s else f"mean={_fmt(s['mean_pct'])}  sd={_fmt(s['sd_pct'])}  Sharpe={_fmt(s['sharpe'])}  historical-mean forecast: mean={_fmt(s['hist_mean_pct'])} Sharpe={_fmt(s['hist_sharpe'])}  CER={_fmt(s['cer_pct'])}  (days={s['days']})"))
    L.append(f"\nTABLE 10 net of IBKR costs (half-spread {half_spread_bps:g} bp at entry, no spread at the close auction; SEC/FINRA/clearing fees from config/costs.toml)   [paper, after 2005: eta(r1) 7.96 gross, 6.52 net]")
    for hs in sorted({half_spread_bps, 0.6, 1.2, 2.4}):
        t10 = table10(r, hs, costs, p["p12"])
        L.append("  " + f"half-spread {hs:g} bp: " + "   ".join(f"{k}: gross {_fmt(v['gross_mean_pct'])} -> net {_fmt(v['net_mean_pct'])} (cost {_fmt(v['cost_pct_per_year'])}/yr)" for k, v in t10.items()))
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--symbol", default="SPY")
    ap.add_argument("--file")
    ap.add_argument("--interval", default="30m")
    ap.add_argument("--label", default="start", choices=["start", "end"])
    ap.add_argument("--half-spread-bps", type=float, default=None, help="default: slippage_bps from config/costs.toml")
    ap.add_argument("--oos-start", default=OOS_START)
    a = ap.parse_args(argv)
    from backtester.engine.costs import CostModel
    costs = CostModel.from_toml()
    p, r = load_returns(a.symbol, a.file, a.interval, a.label)
    print(report(p, r, costs, a.half_spread_bps if a.half_spread_bps is not None else costs.slippage_bps, a.oos_start))
    return 0


if __name__ == "__main__":
    sys.exit(main())
