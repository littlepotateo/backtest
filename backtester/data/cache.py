"""Local bar cache: one Parquet file per symbol and bar size, plus a metadata sidecar.

Bars are indexed by the bar's start time in UTC. Columns: open, high, low, close,
volume, and adj_factor (multiply prices by it to get dividend/split-adjusted prices;
1.0 when unknown).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backtester import paths

COLUMNS = ["open", "high", "low", "close", "volume", "adj_factor"]

# Our bar-size names and the LEAN resolution each maps onto.
INTERVAL_SECONDS = {
    "1m": 60, "2m": 120, "5m": 300, "10m": 600, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400, "1w": 604800,
}
LEAN_RESOLUTION = {"1m": "minute", "1h": "hour", "1d": "daily"}


def to_utc(value) -> pd.Timestamp:
    """A timestamp in UTC, whether `value` is a date, a string or a timestamp."""
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def interval_from_seconds(seconds: int) -> str:
    for name, secs in INTERVAL_SECONDS.items():
        if secs == seconds:
            return name
    raise ValueError(f"unsupported bar size: {seconds} seconds")


def normalise_bars(df: pd.DataFrame, allow_nonpositive: bool = False) -> pd.DataFrame:
    """Return bars in the cache's canonical shape, validated. `allow_nonpositive` is
    for series that are not prices (interest rates can be zero or negative)."""
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    if "adj_factor" not in df.columns:
        df["adj_factor"] = 1.0
    if "volume" not in df.columns:
        df["volume"] = 0.0
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"bars are missing columns: {missing}")
    idx = pd.DatetimeIndex(pd.to_datetime(df.index, utc=True))
    df.index = idx.rename("time")
    df = df[COLUMNS].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["open", "high", "low", "close"])
    if not allow_nonpositive and (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("bars contain zero or negative prices")
    return df


class Cache:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or paths.CACHE)

    def _path(self, symbol: str, interval: str) -> Path:
        if interval not in INTERVAL_SECONDS:
            raise ValueError(f"unknown bar size {interval!r}")
        return self.root / symbol.upper() / f"{interval}.parquet"

    def has(self, symbol: str, interval: str) -> bool:
        return self._path(symbol, interval).exists()

    def save(self, symbol: str, interval: str, bars: pd.DataFrame, *, source: str,
             adjusted: str = "unknown", merge: bool = True,
             allow_nonpositive: bool = False) -> pd.DataFrame:
        """Store bars. With merge=True, new bars are stitched onto what is cached
        (new values win on overlapping timestamps), but only for the same source."""
        bars = normalise_bars(bars, allow_nonpositive)
        path = self._path(symbol, interval)
        if merge and path.exists():
            old_meta = self.meta(symbol, interval)
            if old_meta.get("source") == source:
                bars = normalise_bars(pd.concat([self.load(symbol, interval), bars]), allow_nonpositive)
        path.parent.mkdir(parents=True, exist_ok=True)
        bars.to_parquet(path)
        meta = {
            "symbol": symbol.upper(), "interval": interval, "source": source,
            "adjusted": adjusted, "bars": int(len(bars)),
            "start": bars.index[0].isoformat(), "end": bars.index[-1].isoformat(),
            "market": "usa", "security_type": "equity",
            "lean_resolution": LEAN_RESOLUTION.get(interval),
        }
        path.with_suffix(".json").write_text(json.dumps(meta, indent=2))
        return bars

    def load(self, symbol: str, interval: str, start=None, end=None) -> pd.DataFrame:
        path = self._path(symbol, interval)
        if not path.exists():
            raise FileNotFoundError(
                f"no cached {interval} bars for {symbol.upper()} (looked in {path})")
        df = pd.read_parquet(path)
        if start is not None:
            df = df[df.index >= to_utc(start)]
        if end is not None:
            # an end given as a date includes that whole day
            df = df[df.index < to_utc(end).normalize() + pd.Timedelta(days=1)]
        return df

    def meta(self, symbol: str, interval: str) -> dict:
        path = self._path(symbol, interval).with_suffix(".json")
        try:
            return json.loads(path.read_text()) if path.exists() else {}
        except (ValueError, OSError):
            return {}

    def list(self) -> list[dict]:
        """Metadata of every cached dataset. A file that cannot be read, or that lacks the basic fields, is skipped
        (one damaged file must not take the whole dashboard down)."""
        out = []
        for p in sorted(self.root.glob("*/*.json")):
            try:
                m = json.loads(p.read_text())
            except (ValueError, OSError):
                continue
            if isinstance(m, dict) and all(isinstance(m.get(k), str) and m.get(k) for k in ("symbol", "interval", "start", "end")):
                out.append(m)
        return out


def from_csv(path: str | Path) -> pd.DataFrame:
    """Read bars from a CSV with a time/date column and open/high/low/close[/volume]."""
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]
    time_col = next((c for c in ("time", "datetime", "date", "timestamp") if c in df.columns), None)
    if time_col is None:
        raise ValueError("CSV needs a time, datetime, date or timestamp column")
    if "adj close" in df.columns and "close" in df.columns:
        df["adj_factor"] = df["adj close"] / df["close"]
    df = df.set_index(pd.to_datetime(df[time_col], utc=True))
    return normalise_bars(df)
