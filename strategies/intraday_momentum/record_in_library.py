"""Records the Gao, Han, Li and Zhou (2017) paper in YOUR research library: claimed results as the paper states them (from the full text), the
engine run on the available data (copied into runs/ so the dashboard can open it) and the status. Safe to run more than once.

    .venv/bin/python strategies/intraday_momentum/record_in_library.py        (Windows: .venv\\Scripts\\python ...)
"""

from __future__ import annotations

import shutil
from pathlib import Path

from backtester import paths
from backtester.research import Library

PID = "market-intraday-momentum-2017"
HERE = Path(__file__).resolve().parent
RUN_SOURCE = HERE.parents[1] / "docs" / "replications" / "intraday-momentum" / "run"
RUN_NAME = "20261118-071729-IntradayMomentum"
TITLE = "Market Intraday Momentum"
CLAIMS = [
    "The first half-hour return on the market since the previous day's market close predicts the last half-hour return (SPY, 1993-2013, TAQ).",
    "Table 1: the slope of the last half-hour return on the first (scaled by 100) is 6.94 (Newey-West t 4.08), in-sample R2 1.6%; on the twelfth half-hour 11.8 (t 2.62), R2 1.1%; both predictors R2 2.6%; out-of-sample R2 1.4%, 0.9% and 2.0%.",
    "The predictability is stronger on high-volatility days (R2 3.3% for the combined predictors against 0.6% on low-volatility days), in the financial crisis (R2 6.9% against 1.1% excluding it), on recession days and on days with major news releases (FOMC minutes R2 11.0%).",
    "Table 6: timing with the sign of the first half-hour return earns 6.67% a year with a standard deviation of 6.19% (Sharpe 1.08, skew 0.90, success rate 54.37%), against Always Long -1.11% (Sharpe -0.18) and Buy-and-Hold 6.04% with 20.57% (Sharpe 0.29); using both signals 4.39% with a 77.05% success rate.",
    "Table 7: a mean-variance investor (risk aversion 5, weight between -0.5 and 1.5) earns 6.51% a year (Sharpe 1.16) using the first half-hour return, against 0.46% (Sharpe 0.15) using the historical mean; certainty-equivalent gain 6.02% a year (6.18% with both predictors).",
    "Transaction costs: after decimalisation the timing strategy earns 4.46% net against 6.93% gross; from 2005 (spread about 1.2 basis points) 6.52% net against 7.96% gross.",
    "The pattern also holds for ten other ETFs (DIA, QQQ, IWM, EEM, FXI, EFA, VWO, XLF, IYR, TLT), with in-sample R2 from 1.16% to 8.54% and certainty-equivalent gains up to 17.71% a year.",
]
FINDING = ("The market's first half-hour return (previous close to 10:00) positively predicts its last half-hour return; timing the last half-hour with its sign "
           "earns a high Sharpe ratio after costs, strongest on volatile, high-volume, recession and news days. Explained by infrequent rebalancing and late-informed trading.")


def main() -> None:
    lib = Library(paths.LIBRARY)
    try:
        lib.get(PID)
    except KeyError:
        lib.add(TITLE, year=2017)
    lib.update(PID, title=TITLE, authors="Lei Gao, Yufeng Han, Sophia Zhengzi Li, Guofu Zhou", venue="Working paper (June 2017 version)",
               finding=FINDING, claims=CLAIMS, claims_from_full_text=True)
    target = Path(paths.RUNS) / RUN_NAME
    if not target.exists():
        shutil.copytree(RUN_SOURCE, target)
    entry = lib.link_run(PID, target, strategy="IntradayMomentum")
    lib.set_status(PID, "replicating")
    print(f"{PID}: claims recorded, run {target.name} linked ({entry['period']}), status replicating (mechanics verified; the paper's 1993-2013 sample is not available).")


if __name__ == "__main__":
    main()
