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


# The 18 datasets of Table 1 of the paper (French's file names), in the paper's order. The numbers 7-9 are the three momentum-type sorts:
# 7 short-term reversal = prior 1 month, 8 momentum = prior 12-2, 9 long-term reversal = prior 60-13.
DATASETS = [
    "25_Portfolios_5x5", "25_Portfolios_ME_AC_5x5", "25_Portfolios_ME_BETA_5x5", "25_Portfolios_ME_INV_5x5", "25_Portfolios_ME_NI_5x5",
    "25_Portfolios_ME_OP_5x5", "25_Portfolios_ME_Prior_1_0", "25_Portfolios_ME_Prior_12_2", "25_Portfolios_ME_Prior_60_13",
    "25_Portfolios_ME_RESVAR_5x5", "25_Portfolios_ME_VAR_5x5", "25_Portfolios_OP_INV_5x5", "25_Portfolios_BEME_OP_5x5",
    "25_Portfolios_BEME_INV_5x5", "30_Industry_Portfolios", "32_Portfolios_ME_BEME_INV_2x4x4", "32_Portfolios_ME_BEME_OP_2x4x4",
    "32_Portfolios_ME_OP_INV_2x4x4"]


def parse_portfolio_csv(path: Path) -> pd.DataFrame:
    """The average value-weighted monthly block of a French portfolio file (decimals; -99.99 and -999 become NaN)."""
    return _block(path, "Value Weighted Returns -- Monthly")


def portfolio_dataset(number: int) -> pd.DataFrame:
    """Dataset `number` (1-18) of the paper's Table 1."""
    return parse_portfolio_csv(fetch(DATASETS[number - 1]))


COUNTRIES = {"Australia": "Austrlia", "Belgium": "Belgium", "France": "France", "Germany": "Germany", "Hong Kong": "HongKong", "Italy": "Italy",
             "Japan": "Japan", "Netherlands": "Nethrlnd", "Norway": "Norway", "Singapore": "Singapor", "Spain": "Spain", "Sweden": "Sweden",
             "Switzerland": "Swtzrlnd", "UK": "UK"}


def parse_country_dat(text: str, column: str = "Mkt") -> pd.Series:
    """The country market return (`Mkt`) of the FIRST block of a `F-F_International_Countries` .Dat file, which is the value-weighted
    Dollar-return block. Returns decimals; -99.99 becomes NaN."""
    lines = text.splitlines()
    head = next(i for i, ln in enumerate(lines) if "Dollar" in ln)
    cols = next(lines[i].split() for i in range(head + 1, len(lines)) if column in lines[i].split())
    k = cols.index(column)
    rows, started = {}, False
    for ln in lines[head + 1:]:
        key = ln[:6]
        if key.strip().isdigit() and len(key.strip()) == 6:
            started = True
            vals = ln[6:].replace("-99.99", " -99.99 ").split()          # fixed-width columns can touch when a value is -99.99
            v = float(vals[k])
            rows[pd.Period(f"{key[:4]}-{key[4:6]}", "M")] = float("nan") if v < -99 else v / 100.0
        elif started:
            break
    return pd.Series(rows).sort_index()


def fetch_countries(refresh: bool = False) -> Path:
    """Download and unpack `F-F_International_Countries.zip` into data/external/french/countries/."""
    out = FOLDER / "countries"
    if refresh or not (out / "France.Dat").exists():
        out.mkdir(parents=True, exist_ok=True)
        zpath = FOLDER / "F-F_International_Countries.zip"
        url = BASE + "F-F_International_Countries.zip"
        done = subprocess.run(["curl", "-sSL", "--fail", "-m", "90", "-o", str(zpath), url], capture_output=True, text=True)
        if done.returncode != 0:
            zpath.unlink(missing_ok=True)
            raise RuntimeError(f"Could not download {url}. Download the zip by hand into {FOLDER} ({done.stderr.strip()[:200]})")
        with zipfile.ZipFile(zpath) as z:
            z.extractall(out)
    return out


def country_returns() -> pd.DataFrame:
    """Monthly Dollar-return country market returns (value-weighted), one column per country of the paper's Table 4."""
    folder = fetch_countries()
    return pd.DataFrame({name: parse_country_dat((folder / f"{f}.Dat").read_text(encoding="latin-1")) for name, f in COUNTRIES.items()})
