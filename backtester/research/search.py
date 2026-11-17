"""Searching published papers from the dashboard, using OpenAlex (free, no account or key).

Results carry the abstract where OpenAlex has one, never the full text. Consensus is
available only to Claude Code through its connector, not to this program.
"""

from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

from backtester import settings
from backtester.data.yahoo import explain_network_error, ssl_context

URL = "https://api.openalex.org/works?"
FIELDS = "id,doi,title,publication_year,authorships,primary_location,open_access,abstract_inverted_index,cited_by_count"


class SearchError(ValueError):
    """The search failed. The message says why."""


def rate_limit_message(e: urllib.error.HTTPError, has_key: bool) -> str:
    """What a 429 from the search service actually means, in plain words."""
    try:
        said = json.loads(e.read().decode("utf-8", "replace")).get("message", "")
    except Exception:
        said = ""
    if has_key:
        return "Your paper-search key has used up its allowance for now. Try again later."
    if "no API key" in said or "budget" in said.lower():
        return ("The free daily paper-search allowance for your network is used up (it resets at midnight UTC). "
                "You can add a free key under Search settings to have your own allowance.")
    return "The paper search service is busy (HTTP 429). Wait a minute and search again."


def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    words = {}
    for word, positions in inv.items():
        for p in positions:
            words[p] = word
    return " ".join(words[i] for i in sorted(words))


def parse_results(payload: dict) -> list[dict]:
    out = []
    for w in payload.get("results", []):
        loc = w.get("primary_location") or {}
        src = (loc.get("source") or {}).get("display_name") or ""
        authors = ", ".join((a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or [])[:6])
        if len(w.get("authorships") or []) > 6:
            authors += " et al."
        doi = w.get("doi") or ""
        out.append({"openalex_id": (w.get("id") or "").rsplit("/", 1)[-1], "title": (w.get("title") or "").strip(),
                    "authors": authors, "year": w.get("publication_year"), "venue": src,
                    "url": doi or loc.get("landing_page_url") or w.get("id") or "", "doi": doi,
                    "cited_by": w.get("cited_by_count") or 0, "abstract": _abstract(w.get("abstract_inverted_index")),
                    "open_pdf": (w.get("open_access") or {}).get("oa_url") or ""})
    return [r for r in out if r["title"]]


def search_papers(query: str, limit: int = 10) -> list[dict]:
    query = " ".join((query or "").split())
    if len(query) < 3:
        raise SearchError("Type at least three characters to search.")
    if len(query) > 200:
        raise SearchError("Keep the search under 200 characters.")
    params = urllib.parse.urlencode({"search": query, "per-page": max(1, min(limit, 25)), "select": FIELDS})
    headers = {"User-Agent": "backtester-dashboard"}
    key = settings.get("openalex_api_key")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(URL + params, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20, context=ssl_context()) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise SearchError(rate_limit_message(e, bool(key)))
        if e.code in (401, 403) and key:
            raise SearchError("The paper search service did not accept the saved key. Check it under Search settings.")
        raise SearchError(f"The paper search service returned HTTP {e.code}.")
    except (urllib.error.URLError, socket.timeout, TimeoutError, ssl.SSLError, ConnectionError) as e:
        raise SearchError(str(explain_network_error(e, "the paper search service (OpenAlex)")))
    except json.JSONDecodeError:
        raise SearchError("The paper search service sent a reply that could not be read.")
    return parse_results(payload)
