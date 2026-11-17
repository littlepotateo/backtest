"""Kenneth French data library: download and parse the monthly and daily files used by the paper.

The files are public (https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) and are kept in
data/external/french/ (not committed). Returns in the files are in percent; these functions return decimals.
"""

from __future__ import annotations

import subprocess
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from backtester import paths
from backtester.data.yahoo import ssl_context

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FOLDER = Path(paths.in_root("data/external/french"))


def fetch(name: str, refresh: bool = False) -> Path:
    """Download `<name>_CSV.zip` and return the extracted CSV path."""
    FOLDER.mkdir(parents=True, exist_ok=True)
    zpath = FOLDER / f"{name}_CSV.zip"
    if refresh or not zpath.exists():
        url = BASE + f"{name}_CSV.zip"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60, context=ssl_context()) as r:
                zpath.write_bytes(r.read())
        except (urllib.error.URLError, OSError):
            # the data library's server answers some HTTP/1.1 clients (through some proxies) with a false 404; curl (HTTP/2) works
            done = subprocess.run(["curl", "-sSL", "--fail", "-m", "90", "-o", str(zpath), url], capture_output=True, text=True)
            if done.returncode != 0:
                zpath.unlink(missing_ok=True)
                raise RuntimeError(f"Could not download {url}. Download the zip by hand into {FOLDER} ({done.stderr.strip()[:200]})")
    with zipfile.ZipFile(zpath) as z:
        member = z.namelist()[0]
        out = FOLDER / member
        out.write_bytes(z.read(member))
    return out


def _block(path: Path, header_contains: str | None, ncols: int | None = None, daily: bool = False) -> pd.DataFrame:
    """The first numeric block after the line containing `header_contains` (or the first block in the file)."""
    lines = path.read_text(encoding="latin-1").splitlines()
    start = 0
    if header_contains:
        start = next(i for i, ln in enumerate(lines) if header_contains in ln)
    # the column header is the first line after `start` that starts with a comma
    h = next(i for i in range(start, len(lines)) if lines[i].startswith(","))
    cols = [c.strip() for c in lines[h].split(",")[1:]]
    rows, width = [], 8 if daily else 6
    for ln in lines[h + 1:]:
        key = ln.split(",")[0].strip()
        if not (key.isdigit() and len(key) == width):
            break
        rows.append([key] + [float(x) for x in ln.split(",")[1:len(cols) + 1]])
    df = pd.DataFrame(rows, columns=["date"] + cols).set_index("date")
    df.index = pd.to_datetime(df.index, format="%Y%m%d" if daily else "%Y%m")
    if not daily:
        df.index = df.index.to_period("M")
    df = df.where(df > -99, other=float("nan"))          # -99.99 / -999 mean missing
    return df / 100.0


def factors_monthly() -> pd.DataFrame:
    return _block(fetch("F-F_Research_Data_Factors"), None)


def factors_daily() -> pd.DataFrame:
    return _block(fetch("F-F_Research_Data_Factors_daily"), None, daily=True)


def portfolios_monthly(name: str) -> pd.DataFrame:
    """Value-weighted monthly returns of the portfolios in French's `Portfolios_Formed_on_*` files."""
    return _block(fetch(name), "Value Weight Returns -- Monthly")
