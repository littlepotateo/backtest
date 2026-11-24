"""Whether the cached price data can support a run: every symbol downloaded, and each one's history reaching back far enough
for the run's start date and for the strategy's own requirements (for example a training window). Used by the command line
and by the New backtest form, so both give the same answer and the same suggestion."""

from __future__ import annotations

import pandas as pd

WARMUP_DAYS = 30           # bars the strategy looks back at before it trades (the same allowance as the New backtest form)
OPTIONS_WARMUP_DAYS = 60   # option strategies need a little longer for the volatility estimate


def _day(value) -> str:
    return (str(value or "") or "")[:10]


def coverage(cls, params: dict, symbols: list[str], interval: str, start: str | None, cache, *, options: bool = False) -> dict:
    """{"ok": bool, "problems": [str], "earliest_start": str|None, "earliest_train_end": str|None, "needed_from": str|None}.

    `problems` are plain sentences, each saying what to change. The earliest dates are given only when every symbol is cached."""
    merged = {**cls.params, **(params or {})}
    needed = _day(cls.history_needed(merged)) or None
    problems, firsts = [], {}
    for s in symbols:
        if not cache.has(s, interval):
            problems.append(f"{s} ({interval} bars) is not downloaded yet. Download it on the Data page, or run `bt fetch-yahoo {s}`.")
            continue
        firsts[s] = _day(cache.meta(s, interval).get("start"))
    if problems or not firsts:
        return {"ok": False, "problems": problems or ["No symbols to trade."], "earliest_start": None,
                "earliest_train_end": None, "needed_from": needed}
    latest = max(firsts.values())
    deadline = min(d for d in (start, needed) if d) if (start or needed) else None
    earliest_start = (pd.Timestamp(latest) + pd.Timedelta(days=OPTIONS_WARMUP_DAYS if options else WARMUP_DAYS)).strftime("%Y-%m-%d")
    earliest_train_end = (pd.Timestamp(latest) + pd.DateOffset(months=13)).strftime("%Y-%m-%d") if needed else None
    if deadline:
        late = sorted(s for s, first in firsts.items() if first > deadline)
        if late:
            worst = max(late, key=lambda s: firsts[s])
            if needed and needed < (start or "9999-12-31"):
                problems.append(f"The strategy needs data from {needed} for its training window, but {worst} starts {firsts[worst]}. "
                                f"Set train_end to {earliest_train_end} or later (--param train_end=YYYY-MM-DD) or pick a symbol with longer history.")
            else:
                problems.append(f"{worst} data starts {firsts[worst]}, after the run's start {start}. "
                                f"Start on or after {earliest_start}, or pick a symbol with longer history.")
    return {"ok": not problems, "problems": problems, "earliest_start": earliest_start,
            "earliest_train_end": earliest_train_end, "needed_from": needed}
