"""Which version of the code is running, shown in the page footer and in 'not found' errors."""

import subprocess
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def server_version() -> str:
    """Short git commit of the running checkout, else the package version."""
    root = Path(__file__).resolve().parent.parent
    try:
        sha = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=3)
        if sha.returncode == 0 and sha.stdout.strip():
            return sha.stdout.strip()
    except Exception:
        pass
    try:
        from importlib.metadata import version
        return version("backtester")
    except Exception:
        return "unknown"
