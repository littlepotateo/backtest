"""Checks that the table code recovers a relation PLANTED in simulated half-hour data with the paper's headline parameters:
r13 = 0.0694 r1 + noise (the paper's scaled slope 6.94), r1 with a 0.58% standard deviation and r13 noise chosen so that R2 is about 1.6%.
This tests the machinery, not the paper: the simulated data contain exactly the effect the code is asked to find.

    .venv/bin/python strategies/intraday_momentum/synthetic_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import replicate_tables as T  # noqa: E402

from backtester.engine.costs import CostModel  # noqa: E402


def planted(n: int = 5200, beta: float = 0.0694, sd_r1: float = 0.0058, sd_r13: float = 0.0032, sd_other: float = 0.0018, seed: int = 7,
            start: str = "1993-02-01"):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, sd_other, (n, 13))
    r[:, 0] = rng.normal(0, sd_r1, n)
    resid_sd = np.sqrt(max(sd_r13 ** 2 - (beta * sd_r1) ** 2, 1e-12))
    r[:, 12] = beta * r[:, 0] + rng.normal(0, resid_sd, n)
    dates = pd.bdate_range(start, periods=n).date
    prev, rows = 100.0, []
    for i in range(n):
        p = prev * np.cumprod(1 + r[i])
        rows.append([prev, *p])
        prev = p[-1]
    p = pd.DataFrame(rows, index=pd.Index(dates, name="date"), columns=[f"p{j}" for j in range(14)])
    for j in range(1, 14):
        p[f"v{j}"] = 1.0
    p.attrs["dropped"] = {}
    from halfhours import returns
    return p, returns(p)


def main() -> int:
    p, r = planted()
    print("Simulated SPY-like data with the paper's headline parameters planted (5,200 days):\n")
    print(T.report(p, r, CostModel(slippage_bps=0.6), 0.6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
