"""Where the project's folders are, independent of the folder a command is run from.

Without this, `bt fetch-yahoo` run from one folder caches data under that folder's `data/`,
and `bt serve` run from another looks in a different `data/`, so fetched data seems to vanish.

Order: the BACKTEST_HOME environment variable; else the nearest parent of the current folder
that holds this project's pyproject.toml; else the folder the package was installed from (an
editable install points at the repository); else the current folder.
"""

from __future__ import annotations

import os
from pathlib import Path

MARKER = 'name = "backtester"'


def _is_project(d: Path) -> bool:
    f = d / "pyproject.toml"
    try:
        return f.is_file() and MARKER in f.read_text(encoding="utf-8")
    except OSError:
        return False


def find_root() -> Path:
    env = os.environ.get("BACKTEST_HOME")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd().resolve()
    for d in (cwd, *cwd.parents):
        if _is_project(d):
            return d
    installed = Path(__file__).resolve().parent.parent
    return installed if _is_project(installed) else cwd


ROOT = find_root()


def in_root(relative: str) -> str:
    """An absolute path inside the project folder, as text (for argparse defaults)."""
    return str(ROOT / relative)


CACHE = in_root("data/cache")
RUNS = in_root("runs")
COSTS = in_root("config/costs.toml")
SURFACE = in_root("config/vol_surface.toml")
LIBRARY = in_root("research/library")
