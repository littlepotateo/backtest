"""Runs the engine strategy for every training window of the paper's Tables 2 and 5 (US total market) and compares the Sharpe ratios.

For each training end the strategy is run with zero costs and no cash interest (the paper has none), starting on the last day of the
training window, through 2025-12-31. Two Sharpe ratios are printed: the engine's own (daily returns, annualised with sqrt(252)) and
the one computed from the monthly returns of the engine's equity curve (annualised with sqrt(12)), which is what the paper uses.

    .venv/bin/python strategies/regime_optimal/engine_vs_paper.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from replicate_tables import PAPER_T2, PAPER_T5  # noqa: E402


def run(train_end: str, mode: str, states: int) -> tuple[float, float, Path]:
    day = (pd.Period(train_end, "M").to_timestamp(how="end")).strftime("%Y-%m-%d")
    cmd = [str(ROOT / ".venv" / "bin" / "bt"), "run", str(Path(__file__).parent / "strategy.py"), "--start", day, "--end", "2025-12-31",
           "--no-cash-interest", "--risk-free", "0", "--benchmark", "FFMKT", "--cost-multiplier", "0",
           "--param", f'mode="{mode}"', "--param", f"states={states}", "--param", f'train_end="{day}"']
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, check=True).stdout
    folder = Path(re.search(r"Saved to (\S+)", out).group(1))
    m = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
    e = pd.read_parquet(folder / "equity.parquet")["equity"]
    e.index = pd.to_datetime(e.index, utc=True).tz_convert("America/New_York")
    mon = e.groupby([e.index.year, e.index.month]).last().pct_change().dropna()
    return m["sharpe"], float(mon.mean() / mon.std() * np.sqrt(12)), folder


def main() -> None:
    print("TABLE 2 on the engine: two regimes, total US market, zero costs")
    print(f"{'train end':>9} | {'TSM paper':>9} {'engine(m)':>9} {'engine(d)':>9} | {'OPT paper':>9} {'engine(m)':>9} {'engine(d)':>9}")
    for te, (tsm, opt, *_rest) in PAPER_T2.items():
        t = run(te, "tsm", 2)
        o = run(te, "opt", 2)
        print(f"{te:>9} | {tsm:9.3f} {t[1]:9.3f} {t[0]:9.3f} | {opt:9.3f} {o[1]:9.3f} {o[0]:9.3f}", flush=True)
    print("\nTABLE 5 on the engine: four regimes, total US market, zero costs")
    print(f"{'train end':>9} | {'DSM paper':>9} {'engine(m)':>9} {'engine(d)':>9} | {'OPT paper':>9} {'engine(m)':>9} {'engine(d)':>9}")
    for te, (dsm, opt, *_rest) in PAPER_T5.items():
        d = run(te, "dsm", 4)
        o = run(te, "opt", 4)
        print(f"{te:>9} | {dsm:9.3f} {d[1]:9.3f} {d[0]:9.3f} | {opt:9.3f} {o[1]:9.3f} {o[0]:9.3f}", flush=True)
    print("\n(m) = Sharpe of the engine equity curve's monthly returns, annualised with sqrt(12), as in the paper; (d) = the engine's own daily Sharpe.")


if __name__ == "__main__":
    main()
