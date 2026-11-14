"""Convert the Interactive Brokers connector's price-history output into bars.

The connector returns columnar JSON:
    {"chart_step": 86400, "time": [...ISO strings...], "open": [...], "high": [...],
     "low": [...], "close": [...], "volume": [...]}
Only Claude can call the connector; it saves the JSON to a file and `bt ingest-ibkr`
loads it into the cache.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backtester.data.cache import interval_from_seconds, normalise_bars


def parse_ibkr_history(payload: dict | str | Path) -> tuple[pd.DataFrame, str]:
    """Return (bars, interval) from one connector response (dict, JSON text or file)."""
    if isinstance(payload, Path) or (isinstance(payload, str) and not payload.lstrip().startswith("{")):
        payload = Path(payload).read_text()
    if isinstance(payload, str):
        payload = json.loads(payload)
    for key in ("time", "open", "high", "low", "close"):
        if key not in payload:
            raise ValueError(f"IBKR history is missing '{key}'")
    n = len(payload["time"])
    cols = {k: payload[k] for k in ("open", "high", "low", "close")}
    cols["volume"] = payload.get("volume") or [0.0] * n
    if any(len(v) != n for v in cols.values()):
        raise ValueError("IBKR history columns have different lengths")
    df = pd.DataFrame(cols, index=pd.to_datetime(payload["time"], utc=True))
    return normalise_bars(df), interval_from_seconds(int(payload["chart_step"]))
