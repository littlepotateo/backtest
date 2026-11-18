"""Tables 4, 7 and 8 and Figures 1 and 2 of Zakamulin (2026), by the paper's own method. Run from the project folder:

    .venv/bin/python strategies/regime_optimal/replicate_extra.py [--figures docs/replications/regime-optimal/figures]

Country returns are Dollar-return country market returns (French library) minus the US one-month Treasury bill rate; the paper does not
say which risk-free rate it uses for them. See spec.md for the other assumptions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import diversified as dv  # noqa: E402
import french  # noqa: E402
import replicate_tables as rt  # noqa: E402

PAPER_T4 = {  # country -> (TSM, OPT, wBe)
    "Australia": (0.095, 0.399, 0.54), "Belgium": (0.078, 0.280, 0.14), "France": (-0.239, 0.086, 0.01), "Germany": (0.124, 0.332, -0.07),
    "Hong Kong": (0.083, 0.310, 0.26), "Italy": (-0.226, -0.084, -0.30), "Japan": (0.165, 0.269, -0.37), "Netherlands": (0.168, 0.444, 0.31),
    "Norway": (0.001, 0.224, -0.08), "Singapore": (0.024, 0.438, 0.38), "Spain": (0.123, 0.238, -0.40), "Sweden": (0.071, 0.425, 0.43),
    "Switzerland": (0.127, 0.419, 0.07), "UK": (0.158, 0.350, 0.43)}
PAPER_T4_AVG = (0.054, 0.295, 0.10)
PAPER_T7 = {  # country -> (DSM, OPT, (wBu, wCo, wBe, wRe))
    "Australia": (0.330, 0.448, (1.00, 0.75, 0.39, 0.81)), "Belgium": (0.379, 0.420, (1.00, 0.55, -0.29, 0.65)),
    "France": (-0.084, 0.123, (1.00, 0.60, -0.12, 0.34)), "Germany": (0.157, 0.315, (0.91, 1.00, 0.05, -0.23)),
    "Hong Kong": (0.191, 0.302, (1.00, 0.72, -0.05, 0.84)), "Italy": (-0.207, 0.060, (1.00, 0.40, 0.02, -0.71)),
    "Japan": (0.214, 0.272, (0.72, 1.00, -0.33, -0.23)), "Netherlands": (0.309, 0.441, (1.00, 0.72, 0.13, 0.56)),
    "Norway": (0.151, 0.187, (1.00, 0.44, -0.04, -0.08)), "Singapore": (0.302, 0.407, (0.76, 0.40, -0.43, 1.00)),
    "Spain": (0.123, 0.147, (0.47, 1.00, -0.18, -0.39)), "Sweden": (0.137, 0.504, (1.00, 0.08, 0.21, 0.41)),
    "Switzerland": (0.388, 0.460, (0.87, 1.00, -0.15, 0.41)), "UK": (0.294, 0.377, (0.76, 1.00, 0.34, 0.41))}
PAPER_T7_AVG = (0.192, 0.319)
PAPER_T8 = [  # dataset number - 1 -> (TSM, OPT, DSM, OPT4)
    (0.157, 0.480, 0.449, 0.579), (0.202, 0.489, 0.518, 0.575), (0.181, 0.526, 0.458, 0.590), (0.152, 0.498, 0.474, 0.621),
    (0.193, 0.513, 0.516, 0.620), (0.182, 0.480, 0.518, 0.624), (0.113, 0.443, 0.458, 0.642), (0.175, 0.494, 0.487, 0.638),
    (0.122, 0.509, 0.443, 0.612), (0.198, 0.412, 0.550, 0.708), (0.190, 0.536, 0.523, 0.688), (0.346, 0.576, 0.501, 0.605),
    (0.331, 0.384, 0.490, 0.592), (0.267, 0.570, 0.531, 0.639), (0.283, 0.558, 0.497, 0.660), (0.164, 0.519, 0.484, 0.607),
    (0.229, 0.563, 0.487, 0.665), (0.253, 0.563, 0.540, 0.635)]
PAPER_T8_AVG = (0.208, 0.506, 0.496, 0.628)


def countries_excess() -> pd.DataFrame:
    rf = french.factors_monthly()["RF"]
    c = french.country_returns()
    return c.sub(rf, axis=0).loc["1975-01":"2025-12"]


def tables_4_and_7(verbose: bool = True, end: str = "2025-12") -> tuple[pd.DataFrame, pd.DataFrame]:
    ex = countries_excess().loc[:end]
    rows4, rows7 = [], []
    for name in ex.columns:
        r = ex[name].dropna()
        two, four = rt.evaluate(r, "2003-12", False), rt.evaluate(r, "2003-12", True)
        p4, p7 = PAPER_T4[name], PAPER_T7[name]
        rows4.append({"country": name, "TSM_paper": p4[0], "TSM": two["base"], "OPT_paper": p4[1], "OPT": two["opt"], "wBe_paper": p4[2], "wBe": two["w_opt"][0]})
        rows7.append({"country": name, "DSM_paper": p7[0], "DSM": four["base"], "OPT_paper": p7[1], "OPT": four["opt"],
                      "w_paper": p7[2], "w": tuple(round(float(four["w_opt"][k]), 2) for k in (1, 2, 3, 4))})
    t4, t7 = pd.DataFrame(rows4).set_index("country"), pd.DataFrame(rows7).set_index("country")
    if verbose:
        print(f"TABLE 4 (two states, 14 countries). Training 1975-01 to 2003-12, evaluation 2004-01 to {end}, annualised Sharpe, paper / here")
        print(f"{'':12} | {'TSM':>13} | {'OPT':>13} | {'wBe':>11}")
        for n, x in t4.iterrows():
            print(f"{n:12} | {x.TSM_paper:6.3f}/{x.TSM:6.3f} | {x.OPT_paper:6.3f}/{x.OPT:6.3f} | {x.wBe_paper:5.2f}/{x.wBe:5.2f}")
        a = t4[["TSM", "OPT", "wBe"]].mean()
        print(f"{'Average':12} | {PAPER_T4_AVG[0]:6.3f}/{a.TSM:6.3f} | {PAPER_T4_AVG[1]:6.3f}/{a.OPT:6.3f} | {PAPER_T4_AVG[2]:5.2f}/{a.wBe:5.2f}")
        print(f"  mean absolute difference from the paper: TSM {(t4.TSM - t4.TSM_paper).abs().mean():.3f}, OPT {(t4.OPT - t4.OPT_paper).abs().mean():.3f}")
        print(f"\nTABLE 7 (four states, 14 countries), evaluation to {end}: DSM / OPT, and the OPT weights (Bu, Co, Be, Re)")
        for n, x in t7.iterrows():
            print(f"{n:12} | {x.DSM_paper:6.3f}/{x.DSM:6.3f} | {x.OPT_paper:6.3f}/{x.OPT:6.3f} | paper {x.w_paper} here {x.w}")
        a7 = t7[["DSM", "OPT"]].mean()
        print(f"{'Average':12} | {PAPER_T7_AVG[0]:6.3f}/{a7.DSM:6.3f} | {PAPER_T7_AVG[1]:6.3f}/{a7.OPT:6.3f}")
        print(f"  mean absolute difference from the paper: DSM {(t7.DSM - t7.DSM_paper).abs().mean():.3f}, OPT {(t7.OPT - t7.OPT_paper).abs().mean():.3f}")
    return t4, t7


def table_8(verbose: bool = True, end: str = "2025-12", drop_negative_zero_ni: bool = False) -> pd.DataFrame:
    """`drop_negative_zero_ni`: dataset 5 of French's library has 35 portfolios (5 sizes x 7 net-issue groups, including negative and
    zero issuance) where the paper states 25; this keeps the five positive-issuance groups (a guess, shown as a sensitivity)."""
    rf = french.factors_monthly()["RF"]
    rows = []
    for k in range(1, 19):
        panel = french.portfolio_dataset(k).loc["1963-07":end].sub(rf, axis=0)
        if k == 5 and drop_negative_zero_ni:
            panel = panel[[c for c in panel if "NegNI" not in c and "ZeroNI" not in c]]
        two, four = dv.diversified_returns(panel, "1997-12", False), dv.diversified_returns(panel, "1997-12", True)
        p = PAPER_T8[k - 1]
        rows.append({"dataset": k, "n_assets": two["n_assets"], "TSM_paper": p[0], "TSM": dv.sharpe_of(two["base"]), "OPT_paper": p[1], "OPT": dv.sharpe_of(two["opt"]),
                     "DSM_paper": p[2], "DSM": dv.sharpe_of(four["base"]), "OPT4_paper": p[3], "OPT4": dv.sharpe_of(four["opt"])})
    t8 = pd.DataFrame(rows).set_index("dataset")
    if verbose:
        print(f"\nTABLE 8 (diversified; training 1963-07 to 1997-12, evaluation 1998-01 to {end}){' with dataset 5 cut to 25 portfolios' if drop_negative_zero_ni else ''}, paper / here")
        print(f"{'#':>3} {'N':>3} | {'TSM':>13} | {'OPT':>13} | {'DSM':>13} | {'OPT4':>13}")
        for k, x in t8.iterrows():
            print(f"{k:>3} {int(x.n_assets):>3} | {x.TSM_paper:6.3f}/{x.TSM:6.3f} | {x.OPT_paper:6.3f}/{x.OPT:6.3f} | {x.DSM_paper:6.3f}/{x.DSM:6.3f} | {x.OPT4_paper:6.3f}/{x.OPT4:6.3f}")
        a = t8.mean()
        print(f"{'Avg':>7} | {PAPER_T8_AVG[0]:6.3f}/{a.TSM:6.3f} | {PAPER_T8_AVG[1]:6.3f}/{a.OPT:6.3f} | {PAPER_T8_AVG[2]:6.3f}/{a.DSM:6.3f} | {PAPER_T8_AVG[3]:6.3f}/{a.OPT4:6.3f}")
        print(f"  mean absolute difference from the paper: TSM {(t8.TSM - t8.TSM_paper).abs().mean():.3f}, OPT {(t8.OPT - t8.OPT_paper).abs().mean():.3f}, "
              f"DSM {(t8.DSM - t8.DSM_paper).abs().mean():.3f}, OPT4 {(t8.OPT4 - t8.OPT4_paper).abs().mean():.3f}")
    return t8


def figures(out: Path) -> None:
    from backtester.viz import figures as viz
    mkt = french.factors_monthly()["Mkt-RF"].dropna().loc[:"2025-12"]
    for four, number, bench in ((False, 1, "TSM"), (True, 2, "DSM")):
        s = dv.figure_series(mkt, four)
        print(f"\nFIGURE {number}: OPT vs {bench}, evaluation start 1969-01 to 2012-12 (Sharpe to 2025-12). "
              f"First {s.iloc[0].round(3).to_dict()}, last {s.iloc[-1].round(3).to_dict()}; OPT above {bench} in {(s.OPT > s.benchmark).mean():.0%} of start months")
        for dark in (False, True):
            fig = viz.rolling_sharpe(s["OPT"], s["benchmark"], names=("OPT", bench), dark=dark,
                                     title=f"Figure {number}: rolling out-of-sample Sharpe, OPT vs {bench} (US market)")
            viz.save(fig, out / f"figure{number}_{'dark' if dark else 'light'}.html")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--figures", default=None, help="folder for Figures 1 and 2 (HTML)")
    ap.add_argument("--skip-tables", action="store_true")
    a = ap.parse_args()
    if not a.skip_tables:
        tables_4_and_7()
        print("\nSENSITIVITY: the paper's country results are reproduced when the evaluation window stops one year earlier")
        tables_4_and_7(end="2024-12")
        table_8()
        print("\nSENSITIVITY: dataset 5 cut to 25 portfolios, and the evaluation window ending 2024-12")
        table_8(drop_negative_zero_ni=True)
        table_8(end="2024-12")
    if a.figures:
        out = Path(a.figures)
        out.mkdir(parents=True, exist_ok=True)
        figures(out)


if __name__ == "__main__":
    main()
