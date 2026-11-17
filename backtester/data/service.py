"""Downloading, importing, updating and removing market data. Used by both the `bt`
command and the dashboard, so they behave the same way. Every function reports progress
through `log` and raises DataError (with a plain message) on failure."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

import pandas as pd

from backtester.data.cache import INTERVAL_SECONDS, Cache, from_csv, normalise_bars
from backtester.data.ibkr import parse_ibkr_history
from backtester.data.yahoo import DataError, clamp_start, fetch_yahoo

RATE_SYMBOL = "^IRX"
NON_PRICE = {RATE_SYMBOL}                 # series that may be zero or negative
SYMBOL = re.compile(r"^[A-Za-z0-9^.=-]{1,15}$")
Log = Callable[[str], None]


def _quiet(_: str) -> None:
    return None


def clean_symbols(text: str) -> list[str]:
    """'spy, qqq  ^vix' -> ['SPY', 'QQQ', '^VIX'] (rejects anything that is not a plain ticker)."""
    out = []
    for raw in re.split(r"[\s,;]+", text or ""):
        if not raw:
            continue
        if not SYMBOL.match(raw):
            raise DataError(f"'{raw}' does not look like a ticker symbol.", "BT-DATA-004")
        if raw.upper() not in out:
            out.append(raw.upper())
    if not out:
        raise DataError("Enter at least one symbol, for example SPY.", "BT-DATA-004")
    if len(out) > 40:
        raise DataError("Fetch at most 40 symbols at a time.", "BT-DATA-005")
    return out


def fetch_symbol(cache: Cache, symbol: str, interval: str = "1d", start: str | None = None,
                 log: Log = _quiet) -> dict:
    """Download one symbol from Yahoo and merge it into the cache. Returns a summary."""
    symbol = symbol.upper()
    start, note = clamp_start(interval, start)
    log(f"Downloading {symbol} ({interval}) from Yahoo Finance…")
    if note:
        log(note)
    bars = fetch_yahoo(symbol, interval, start or "1990-01-01", allow_nonpositive=symbol in NON_PRICE)
    saved = cache.save(symbol, interval, bars, source="yahoo",
                       adjusted="not a price" if symbol in NON_PRICE else "split-adjusted; adj_factor adds dividends",
                       allow_nonpositive=symbol in NON_PRICE)
    msg = (f"{symbol} {interval}: {len(saved):,} bars cached "
           f"({saved.index[0].date()} to {saved.index[-1].date()})")
    log(msg)
    return {"symbol": symbol, "interval": interval, "bars": int(len(saved)),
            "start": str(saved.index[0].date()), "end": str(saved.index[-1].date()), "message": msg}


def fetch_rates(cache: Cache, start: str = "1990-01-01", log: Log = _quiet) -> dict:
    r = fetch_symbol(cache, RATE_SYMBOL, "1d", start, log)
    latest = float(cache.load(RATE_SYMBOL, "1d")["close"].iloc[-1])
    r["message"] = f"13-week Treasury bill yield: {r['bars']:,} days cached ({r['start']} to {r['end']}), latest {latest:.2f}%"
    log(r["message"])
    return r


def fetch_many(cache: Cache, symbols: list[str], interval: str = "1d", start: str | None = None,
               log: Log = _quiet) -> dict:
    """Fetch several symbols, carrying on past failures. Returns {'done': [...], 'failed': [(symbol, message)]}."""
    done, failed = [], []
    for s in symbols:
        try:
            done.append(fetch_symbol(cache, s, interval, start, log))
        except DataError as e:
            log(f"{s}: FAILED. {e}")
            failed.append((s, str(e)))
    return {"done": done, "failed": failed}


def update_all(cache: Cache, log: Log = _quiet) -> dict:
    """Bring every cached Yahoo dataset up to date (re-downloading from a week before its last bar)."""
    done, failed = [], []
    items = [m for m in cache.list() if m.get("source") == "yahoo"]
    if not items:
        log("Nothing to update: no Yahoo datasets are cached yet.")
    for m in items:
        try:
            start = (pd.Timestamp(m["end"]) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            done.append(fetch_symbol(cache, m["symbol"], m["interval"], start, log))
        except DataError as e:
            log(f"{m['symbol']}: FAILED. {e}")
            failed.append((m["symbol"], str(e)))
    return {"done": done, "failed": failed}


def import_file(cache: Cache, filename: str, content: bytes, symbol: str | None = None,
                interval: str | None = None, log: Log = _quiet) -> dict:
    """Import prices from a dropped file: a CSV with date/open/high/low/close[/volume], or the JSON the
    Interactive Brokers connector returns. The symbol comes from the form or the file name (SPY.csv)."""
    name = Path(filename).name
    stem = re.sub(r"[^A-Za-z0-9^.=-]+", "", Path(name).stem.split("_")[0].split("-")[0]).upper()
    symbol = (symbol or stem or "").upper()
    if not SYMBOL.match(symbol):
        raise DataError(f"Could not tell which symbol {name} holds. Enter the symbol and import again.", "BT-DATA-006")
    suffix = Path(name).suffix.lower()
    log(f"Reading {name} as {symbol}…")
    try:
        if suffix == ".json":
            bars, found = parse_ibkr_history(json.loads(content.decode("utf-8")))
            interval, source = interval or found, "ibkr"
        elif suffix in (".csv", ".txt"):
            tmp = cache.root / f".import-{symbol}.csv"
            cache.root.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(content)
            try:
                bars = from_csv(tmp)
            finally:
                tmp.unlink(missing_ok=True)
            interval, source = interval or _guess_interval(bars), "csv"
        else:
            raise DataError(f"{name}: only .csv and .json price files can be imported.", "BT-DATA-007")
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise DataError(f"{name} could not be read as price data: {e}", "BT-DATA-008")
    if interval not in INTERVAL_SECONDS:
        raise DataError(f"Unknown bar size {interval!r}.", "BT-DATA-003")
    saved = cache.save(symbol, interval, bars, source=source)
    msg = f"{symbol} {interval}: {len(saved):,} bars from {name} ({saved.index[0].date()} to {saved.index[-1].date()})"
    log(msg)
    return {"symbol": symbol, "interval": interval, "bars": int(len(saved)), "source": source, "message": msg}


def _guess_interval(bars: pd.DataFrame) -> str:
    gap = bars.index.to_series().diff().dropna().median()
    secs = gap.total_seconds() if pd.notna(gap) else 86400
    best = min(INTERVAL_SECONDS, key=lambda k: abs(INTERVAL_SECONDS[k] - secs))
    return best if abs(INTERVAL_SECONDS[best] - secs) < INTERVAL_SECONDS[best] * 0.3 else "1d"


def delete_dataset(cache: Cache, symbol: str, interval: str) -> None:
    p = cache._path(symbol, interval)
    if not p.exists():
        raise DataError(f"{symbol} {interval} is not cached.", "BT-DATA-009")
    p.unlink()
    p.with_suffix(".json").unlink(missing_ok=True)
    try:
        p.parent.rmdir()
    except OSError:
        pass


def dataset_table(cache: Cache) -> list[dict]:
    """Cached datasets for display, with how old each is."""
    today = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
    rows = []
    for m in cache.list():
        end = pd.Timestamp(m["end"][:10])
        age = int((today - end).days)
        rows.append({**m, "start": m["start"][:10], "end": m["end"][:10], "age_days": age,
                     "stale": age > (5 if m["interval"] == "1d" else 3),
                     "kind": "rate" if m["symbol"] in NON_PRICE else "index" if m["symbol"].startswith("^") else "prices"})
    return sorted(rows, key=lambda r: (r["kind"] != "prices", r["symbol"], r["interval"]))
