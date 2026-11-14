"""Yahoo Finance bars (fallback source: long daily history, recent intraday).

Yahoo's OHLC is split-adjusted; `adjclose` also adjusts for dividends, so
adj_factor = adjclose / close. Intraday responses carry no adjclose (factor 1.0).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

import pandas as pd

from backtester.data.cache import normalise_bars, to_utc

_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
_INTERVALS = {"1m": "1m", "2m": "2m", "5m": "5m", "15m": "15m", "30m": "30m",
              "1h": "60m", "1d": "1d", "1w": "1wk"}


def parse_yahoo_chart(payload: dict) -> pd.DataFrame:
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise ValueError(f"Yahoo error: {chart['error']}")
    result = chart["result"][0]
    stamps = result.get("timestamp")
    if not stamps:
        raise ValueError("Yahoo returned no bars")
    quote = result["indicators"]["quote"][0]
    df = pd.DataFrame({k: quote[k] for k in ("open", "high", "low", "close", "volume")},
                      index=pd.to_datetime(stamps, unit="s", utc=True))
    adj = result["indicators"].get("adjclose")
    if adj:
        df["adj_factor"] = pd.Series(adj[0]["adjclose"], index=df.index) / df["close"]
    df = df.dropna(subset=["open", "high", "low", "close"])
    df["volume"] = df["volume"].fillna(0)
    if "adj_factor" in df:
        df["adj_factor"] = df["adj_factor"].fillna(1.0)
    return normalise_bars(df)


def fetch_yahoo(symbol: str, interval: str = "1d", start=None, end=None,
                timeout: float = 30) -> pd.DataFrame:
    if interval not in _INTERVALS:
        raise ValueError(f"Yahoo does not offer {interval} bars")
    start_ts = int(to_utc(start or "1990-01-01").timestamp())
    end_ts = int((to_utc(end).normalize() + pd.Timedelta(days=1)).timestamp()) if end \
        else int(pd.Timestamp.now(tz="UTC").timestamp())
    query = urllib.parse.urlencode({"period1": start_ts, "period2": end_ts,
                                    "interval": _INTERVALS[interval], "events": "div,splits"})
    req = urllib.request.Request(_URL.format(symbol=urllib.parse.quote(symbol), query=query),
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_yahoo_chart(json.load(resp))
