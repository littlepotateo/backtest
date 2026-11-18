"""Figures for the intraday momentum replication, written to docs/replications/intraday-momentum/figures/ as standalone HTML.

    .venv/bin/python strategies/intraday_momentum/make_figures.py --symbol SPY
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import predict  # noqa: E402
import replicate_tables as T  # noqa: E402
import signals  # noqa: E402

from backtester import paths, viz  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="SPY")
    ap.add_argument("--file")
    ap.add_argument("--out", default=str(Path(paths.ROOT) / "docs" / "replications" / "intraday-momentum" / "figures"))
    ap.add_argument("--oos-start", default=T.OOS_START)
    a = ap.parse_args(argv)
    p, r = T.load_returns(a.symbol, a.file)
    out = Path(a.out)
    written = []
    d = r[["r1", "r12", "r13"]].dropna()
    eta = signals.strategy_returns(signals.timing_signal(d["r1"]), d["r13"])
    always = d["r13"]
    curve = lambda x: (1 + x).cumprod().rename(None)
    idx = pd.to_datetime(pd.Index(d.index))
    e, b = curve(eta), curve(always)
    e.index = b.index = idx
    written.append(viz.save(viz.equity_and_drawdown(e, b, "Timing on the first half-hour return, eta(r1), against Always Long (last half-hour only)",
                                                    names=("eta(r1)", "Always Long")), out / "timing_equity.html"))
    if "v1" in p:
        vol = p[[f"v{j}" for j in range(1, 14)]].mean()
        vol.index = range(1, 14)
        written.append(viz.save(viz.intraday_profile(vol, "Average SPY volume by half-hour (Figure 2 of the paper, this sample)", "Shares"), out / "volume_profile.html"))
    try:
        f = predict.recursive_forecast(d["r13"], d[["r1", "r12"]], pd.Timestamp(a.oos_start).date())
        coefs = f[["beta_r1", "beta_r12"]] * 100
        coefs.index = pd.to_datetime(pd.Index(coefs.index))
        written.append(viz.save(viz.coefficient_over_time(coefs.rename(columns={"beta_r1": "r1 coefficient (x100)", "beta_r12": "r12 coefficient (x100)"}),
                                                          "Recursively estimated coefficients (Figure 1 of the paper)"), out / "coefficients.html"))
    except ValueError as e:
        print(f"coefficient figure skipped: {e}")
    for w in written:
        print("wrote", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
