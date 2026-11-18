"""Half-hour prices and returns for the intraday momentum study (Gao, Han, Li and Zhou, 2017, section 2).

The regular session 09:30-16:00 New York time is split into 13 half-hours. `p_j` is the price at the END of half-hour j (so `p_1`
is the 10:00 price and `p_13` the 16:00 close); `p_0` is the previous trading day's `p_13`. Returns follow equation (1):
`r_j = p_j / p_(j-1) - 1`, so the first half-hour return `r_1` includes the overnight gap.

A day is kept only if all 13 half-hours have at least one bar. Half-days (13:00 close) and days with a missing half-hour are dropped
and listed in `result.attrs["dropped"]`. The paper drops days with fewer than 500 trades; trade counts are not in bar data, so the
number of bars is used instead (assumption, written down in spec.md).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"
SESSION_OPEN_MINUTES = 9 * 60 + 30
HALF_HOURS = 13


def to_halfhours(bars: pd.DataFrame, tz: str = NY, label: str = "start") -> pd.DataFrame:
    """Bars (any size up to 30 minutes, UTC index) to one row per complete trading day with columns p0..p13 and, when the bars have
    volume, v1..v13. `label` says whether a bar's timestamp is its start (Yahoo, IBKR: default) or its end."""
    if not isinstance(bars, pd.DataFrame) or "close" not in bars.columns:
        raise ValueError("bars must be a DataFrame with a 'close' column and a time index")
    if label not in ("start", "end"):
        raise ValueError("label must be 'start' or 'end'")
    df = bars.sort_index()
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    if label == "end" and len(idx) > 1:
        step = pd.Series(idx).diff().dropna().median()
        idx = idx - step
    local = idx.tz_convert(tz)
    minutes = local.hour * 60 + local.minute - SESSION_OPEN_MINUTES
    keep = (minutes >= 0) & (minutes < 30 * HALF_HOURS)
    work = pd.DataFrame({"close": df["close"].to_numpy(), "bucket": (minutes // 30) + 1, "day": local.date}, index=idx)[keep]
    if "volume" in df.columns:
        work["volume"] = df["volume"].to_numpy()[keep]
    sessions = sorted({d for d in local.date})
    rows, dropped = {}, {}
    for day, g in work.groupby("day", sort=True):
        last = g.groupby("bucket")["close"].last()
        if len(last) < HALF_HOURS:
            dropped[day.isoformat()] = f"incomplete session ({len(last)} of {HALF_HOURS} half-hours)"
            continue
        row = {f"p{j}": float(last[j]) for j in range(1, HALF_HOURS + 1)}
        if "volume" in g:
            vol = g.groupby("bucket")["volume"].sum()
            row.update({f"v{j}": float(vol[j]) for j in range(1, HALF_HOURS + 1)})
        rows[day] = row
    for day in sessions:                                                         # sessions seen only outside the regular hours
        if day not in rows and day.isoformat() not in dropped and (work["day"] == day).sum() == 0:
            dropped[day.isoformat()] = "no regular-session bars"
    out = pd.DataFrame.from_dict(rows, orient="index")
    if out.empty:
        out = pd.DataFrame(columns=[f"p{j}" for j in range(1, HALF_HOURS + 1)])
    out.index = pd.Index(list(out.index), name="date")
    previous_session = {d: (sessions[i - 1] if i else None) for i, d in enumerate(sessions)}
    out.insert(0, "p0", [out["p13"].get(previous_session.get(d), np.nan) if previous_session.get(d) is not None else np.nan
                         for d in out.index])
    out.attrs["dropped"] = dropped
    return out


def returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Equation (1): r1..r13 from p0..p13 (r1 is the previous close to the 10:00 price)."""
    out = pd.DataFrame(index=prices.index)
    for j in range(1, HALF_HOURS + 1):
        out[f"r{j}"] = prices[f"p{j}"] / prices[f"p{j - 1}"] - 1
    return out
