"""Builds the price series the engine needs from Kenneth French's DAILY market excess return (Mkt-RF) and saves it to the cache.

The paper's strategy return is R = w * r, where r is the market EXCESS return (market minus the risk-free rate) and the rest of the
wealth earns the risk-free rate. If the engine trades an index built from excess returns, holding a fraction w of equity in it and
leaving the rest in cash earning nothing gives exactly R = w * r, so the engine's Sharpe ratio is the paper's Sharpe ratio (use
--risk-free 0 --no-cash-interest). Bars: one per trading day; open = previous close, so a fill at the next open is a fill at the last
close (the paper assumes the weight for month t is set at the end of month t-1).

    .venv/bin/python strategies/regime_optimal/make_data.py            # symbol FFMKT, sample ending 2025-12-31 as in the paper
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import french  # noqa: E402

from backtester.data.cache import Cache, from_csv  # noqa: E402
from backtester import paths  # noqa: E402

SYMBOL, END = "FFMKT", "2025-12-31"


def build() -> pd.DataFrame:
    x = french.factors_daily()["Mkt-RF"].dropna().loc[:END]
    close = 100.0 * (1 + x).cumprod()
    prev = close.shift(1).fillna(100.0)
    df = pd.DataFrame({"open": prev, "high": pd.concat([prev, close], axis=1).max(axis=1),
                       "low": pd.concat([prev, close], axis=1).min(axis=1), "close": close, "volume": 1.0})
    # 21:00 UTC is after the US close in every season, so the New York date of each bar is the French date
    df.insert(0, "time", [f"{d:%Y-%m-%d} 21:00:00" for d in df.index])
    return df.reset_index(drop=True)


def main() -> None:
    df = build()
    tmp = Path(paths.in_root("data/external/french")) / f"{SYMBOL}.csv"
    df.to_csv(tmp, index=False)
    saved = Cache().save(SYMBOL, "1d", from_csv(tmp), source="Kenneth French data library, daily Mkt-RF (excess return index)",
                         adjusted="not applicable: index of excess returns")
    print(f"{SYMBOL} 1d: {len(saved)} bars cached ({saved.index[0].date()} to {saved.index[-1].date()})")


if __name__ == "__main__":
    main()
