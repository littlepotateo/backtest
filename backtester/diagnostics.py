"""Self-checks for the installation, the project folders and the internet connection.
Used by `bt doctor` and the dashboard's Data page."""

from __future__ import annotations

import importlib
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request

from backtester import paths
from backtester.data.cache import Cache
from backtester.data.yahoo import explain_network_error, ssl_context

REQUIRED = ["numpy", "pandas", "pyarrow", "scipy", "fastapi", "uvicorn", "jinja2", "markdown", "plotly", "multipart", "certifi", "pypdf"]


def missing_packages() -> list[str]:
    """Required packages that cannot be imported (empty when the installation is complete)."""
    missing = []
    for mod in REQUIRED:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    return missing


def _check(name: str, ok: bool, detail: str, hint: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail, "hint": hint}


def _reach(url: str, label: str) -> dict:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=ssl_context()) as r:
            code = r.status
        return _check(f"Reach {label}", True, f"answered HTTP {code} in {time.time() - t0:.1f}s")
    except urllib.error.HTTPError as e:                     # the server answered, so the connection works; the code says if it helped
        hint = ""
        if e.code == 429:
            hint = ("The service is limiting requests from this network. For paper search, add a free key under OpenAlex settings "
                    "on the Research page; for prices, wait and try again.")
        return _check(f"Reach {label}", e.code < 400, f"answered HTTP {e.code} in {time.time() - t0:.1f}s", hint)
    except (urllib.error.URLError, socket.timeout, TimeoutError, ssl.SSLError, ConnectionError) as e:
        err = explain_network_error(e, label)
        return _check(f"Reach {label}", False, str(err))


def run_checks(cache: Cache | None = None, network: bool = True) -> list[dict]:
    cache = cache or Cache()
    out = [_check("Python version", sys.version_info >= (3, 11), sys.version.split()[0],
                  "Python 3.11 or newer is required. Install a newer Python and rebuild the .venv folder.")]
    out.append(_check("Project folder", (paths.ROOT / "pyproject.toml").exists(), str(paths.ROOT),
                      "Run commands from inside the cloned 'backtest' folder, or set BACKTEST_HOME to it."))
    missing = missing_packages()
    out.append(_check("Installed packages", not missing, "all present" if not missing else "missing: " + ", ".join(missing),
                      'Run: .venv/bin/pip install -e ".[dev]" (from the project folder).'))
    for label, folder in (("Data folder writable", cache.root), ("Runs folder writable", paths.ROOT / "runs")):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            ok = os.access(folder, os.W_OK)
        except OSError:
            ok = False
        out.append(_check(label, ok, str(folder), "Check the folder's permissions."))
    n = len(cache.list())
    out.append(_check("Cached datasets", True, f"{n} cached in {cache.root}" if n else f"none yet (looking in {cache.root})"))
    if network:
        out.append(_reach("https://query1.finance.yahoo.com/v8/finance/chart/SPY?range=1d&interval=1d", "Yahoo Finance (prices)"))
        out.append(_reach("https://api.openalex.org/works?per-page=1&select=id", "OpenAlex (paper search)"))
    return out


def print_report(cache: Cache | None = None) -> bool:
    ok_all = True
    for c in run_checks(cache):
        mark = "ok  " if c["ok"] else "FAIL"
        print(f"[{mark}] {c['name']}: {c['detail']}")
        if not c["ok"] and c["hint"]:
            print(f"         {c['hint']}")
        ok_all &= c["ok"]
    print("\nEverything looks fine." if ok_all else "\nSomething needs attention (see the FAIL lines above).")
    return ok_all
