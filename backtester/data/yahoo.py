"""Yahoo Finance bars (fallback source: long daily history, recent intraday).

Yahoo's OHLC is split-adjusted; `adjclose` also adjusts for dividends, so
adj_factor = adjclose / close. Intraday responses carry no adjclose (factor 1.0).

Every failure is turned into a DataError with a plain-language message, so a failed
download is never silent or a bare traceback.
"""

from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from backtester.data.cache import normalise_bars, to_utc

_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
_INTERVALS = {"1m": "1m", "2m": "2m", "5m": "5m", "15m": "15m", "30m": "30m",
              "1h": "60m", "1d": "1d", "1w": "1wk"}
# How far back Yahoo keeps intraday bars, in days.
INTRADAY_LIMIT_DAYS = {"1m": 7, "2m": 59, "5m": 59, "15m": 59, "30m": 59, "1h": 729}


class DataError(ValueError):
    """A data download or import failed. The message says why and what to try."""


def ssl_context() -> ssl.SSLContext:
    """TLS settings that carry their own certificate list (certifi), because Python installed
    from python.org on macOS has none until a separate script is run."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def explain_network_error(e: Exception, what: str = "Yahoo Finance") -> DataError:
    reason = getattr(e, "reason", e)
    text = str(reason)
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 404:
            return DataError(f"{what} has no data for that symbol (HTTP 404). Check the ticker; index symbols start with ^.")
        if e.code == 429:
            return DataError(f"{what} is limiting requests (HTTP 429). Wait a minute and try again.")
        if e.code in (400, 422):
            return DataError(f"{what} rejected the request (HTTP {e.code}). For intraday bars it only keeps recent days.")
        return DataError(f"{what} returned HTTP {e.code}.")
    if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in text:
        return DataError("The secure connection could not be verified (certificate error). On a Mac with Python from python.org, "
                         "run the 'Install Certificates.command' file in /Applications/Python 3.x/, or run "
                         "`pip install --upgrade certifi`. A company network or VPN that inspects traffic can also cause this.")
    if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in text:
        return DataError(f"{what} did not answer in time. Check the internet connection, VPN or firewall, then try again.")
    if isinstance(reason, socket.gaierror) or "Name or service not known" in text or "nodename nor servname" in text:
        return DataError(f"Could not find {what} on the network. Check that this computer is online.")
    return DataError(f"Could not reach {what}: {text}")


def parse_yahoo_chart(payload: dict, allow_nonpositive: bool = False) -> pd.DataFrame:
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise DataError(f"Yahoo error: {chart['error'].get('description') or chart['error']}")
    result = (chart.get("result") or [None])[0]
    if not result or not result.get("timestamp"):
        raise DataError("Yahoo returned no bars for that symbol and period.")
    quote = result["indicators"]["quote"][0]
    df = pd.DataFrame({k: quote[k] for k in ("open", "high", "low", "close", "volume")},
                      index=pd.to_datetime(result["timestamp"], unit="s", utc=True))
    adj = result["indicators"].get("adjclose")
    if adj:
        df["adj_factor"] = pd.Series(adj[0]["adjclose"], index=df.index) / df["close"]
    df = df.dropna(subset=["open", "high", "low", "close"])
    if df.empty:
        raise DataError("Yahoo returned only empty bars for that symbol and period.")
    df["volume"] = df["volume"].fillna(0)
    if "adj_factor" in df:
        df["adj_factor"] = df["adj_factor"].fillna(1.0)
    try:
        return normalise_bars(df, allow_nonpositive)
    except ValueError as e:
        raise DataError(f"The downloaded data failed validation: {e}")


def clamp_start(interval: str, start):
    """(start, note): the start date moved forward if Yahoo does not keep intraday bars that far back."""
    limit = INTRADAY_LIMIT_DAYS.get(interval)
    if not limit:
        return start, None
    earliest = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=limit)
    if start is None or to_utc(start) < earliest:
        return earliest.strftime("%Y-%m-%d"), (
            f"Yahoo keeps only about {limit} days of {interval} bars, so the start was moved to {earliest:%Y-%m-%d}.")
    return start, None


def fetch_yahoo(symbol: str, interval: str = "1d", start=None, end=None,
                timeout: float = 30, allow_nonpositive: bool = False) -> pd.DataFrame:
    if interval not in _INTERVALS:
        raise DataError(f"Yahoo does not offer {interval} bars. Choose one of: {', '.join(_INTERVALS)}.")
    symbol = (symbol or "").strip()
    if not symbol:
        raise DataError("Enter a symbol, for example SPY.")
    start_ts = int(to_utc(start or "1990-01-01").timestamp())
    end_ts = int((to_utc(end).normalize() + pd.Timedelta(days=1)).timestamp()) if end \
        else int(pd.Timestamp.now(tz="UTC").timestamp())
    query = urllib.parse.urlencode({"period1": start_ts, "period2": end_ts,
                                    "interval": _INTERVALS[interval], "events": "div,splits"})
    req = urllib.request.Request(_URL.format(symbol=urllib.parse.quote(symbol), query=query),
                                 headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, socket.timeout, TimeoutError, ssl.SSLError, ConnectionError) as e:
        raise explain_network_error(e)
    except json.JSONDecodeError:
        raise DataError("Yahoo sent a reply that could not be read. Try again in a minute.")
    return parse_yahoo_chart(payload, allow_nonpositive)
