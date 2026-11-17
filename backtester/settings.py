"""Local settings kept in one file that is never committed (it can hold a secret key).

The file is `settings.local.json` in the project folder, readable only by you. The dashboard can
save a value but never shows a saved key back.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from backtester import paths

KEYS = {"openalex_api_key"}
ENV = {"openalex_api_key": "OPENALEX_API_KEY"}


def _file() -> Path:
    return paths.ROOT / "settings.local.json"


def load() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def get(name: str) -> str:
    """A saved value, or the matching environment variable, or empty."""
    return (load().get(name) or os.environ.get(ENV.get(name, ""), "") or "").strip()


def set_value(name: str, value: str) -> None:
    if name not in KEYS:
        raise KeyError(name)
    data = load()
    value = (value or "").strip()
    if value:
        data[name] = value
    else:
        data.pop(name, None)
    f = _file()
    f.write_text(json.dumps(data), encoding="utf-8")
    try:
        f.chmod(0o600)
    except OSError:
        pass


def is_set(name: str) -> bool:
    return bool(get(name))
