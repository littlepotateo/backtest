"""Records the Zakamulin (2026) paper in YOUR research library: claimed results as the paper states them (from the full text),
the validated run (copied into runs/ so the dashboard can open it) and the replication status. Safe to run more than once.

    .venv/bin/python strategies/regime_optimal/record_in_library.py        (Windows: .venv\\Scripts\\python ...)

If the paper is already in your library under the id `rethinking-trend-following-optimal-2026` (made by dropping the PDF), that
entry is updated, not duplicated; your own notes file and PDF are kept. Claims already recorded are REPLACED by the list below.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from backtester import paths
from backtester.research import Library

PID = "rethinking-trend-following-optimal-2026"
HERE = Path(__file__).resolve().parent
RUN_SOURCE = HERE.parents[1] / "docs" / "replications" / "regime-optimal" / "run"
RUN_NAME = "20261117-145959-RegimeOptimal"
FULL_TITLE = "Rethinking Trend Following: Optimal Regime-Dependent Allocation"
CLAIMS = [
    "Optimal regime-dependent allocation delivers economically meaningful and robust improvements in out-of-sample risk-adjusted performance relative to the time-series momentum strategy of Moskowitz, Ooi, and Pedersen (2012) and the dynamic speed momentum strategy of Goulding, Harvey, and Mazzoleni (2023).",
    "Table 2 (US total market, two regimes, training from 1926-07 ending 1968-12, evaluation to 2025-12): TSM Sharpe 0.413, OPT Sharpe 0.559 with weights (Bull 1.00, Bear 0.05). Across eight training windows OPT exceeds TSM by 0.146 to 0.233.",
    "Table 5 (US total market, four regimes, training ending 1968-12): DSM Sharpe 0.504, OPT Sharpe 0.625 with weights (1.00, 0.61, 0.01, 0.09). OPT exceeds DSM in all eight training windows (DIF 0.112 to 0.228).",
    "Table 3 (four US portfolios, training to 2003-12): OPT beats TSM for large, small, value and growth portfolios; estimated Bear weights range from 0.03 (value) to 0.31 (small).",
    "Tables 4 and 7 (14 developed countries): average Sharpe 0.054 under TSM versus 0.295 under OPT; 0.192 under DSM versus 0.319 under OPT.",
    "Table 8 (18 diversified portfolio datasets, training 1963-07 to 1997-12): average two-regime TSM 0.208 versus OPT 0.506; four-regime DSM 0.496 versus OPT 0.628; OPT is higher in all 18 datasets.",
]
FINDING = ("Derives Sharpe-optimal regime-dependent exposures in closed form (weights proportional to the regime's mean excess return "
           "divided by its mean squared excess return) and shows out-of-sample gains over time-series momentum (TSM) and dynamic speed "
           "momentum (DSM), mainly because Bear-regime exposure should be near zero rather than -1.")


def main() -> None:
    lib = Library(paths.LIBRARY)
    try:
        lib.get(PID)
    except KeyError:
        lib.add("Rethinking Trend Following: Optimal", year=2026)          # the id comes from the title and year
    lib.update(PID, title=FULL_TITLE, authors="Valeriy Zakamulin", venue="Working paper, University of Agder (9 March 2026)",
               finding=FINDING, claims=CLAIMS, claims_from_full_text=True)
    target = Path(paths.RUNS) / RUN_NAME
    if not target.exists():
        shutil.copytree(RUN_SOURCE, target)
    entry = lib.link_run(PID, target, strategy="RegimeOptimal")
    lib.set_status(PID, "partly replicated")
    print(f"{PID}: claims recorded, run {target.name} linked ({entry['period']}), status partly replicated.")


if __name__ == "__main__":
    main()
