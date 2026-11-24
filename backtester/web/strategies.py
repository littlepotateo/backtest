"""Finding strategy files and reading their settings without running them (static parsing)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from backtester.data.cache import Cache
from backtester.options.surface import VOL_INDEX

RATE = "^IRX"


def _literal(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except Exception:                      # not a plain literal (or too odd to read): treated as not set
        return None


def _symbols(value) -> list[str]:
    """A list of ticker strings from whatever the file declared (a single string counts as one ticker)."""
    if isinstance(value, str):
        value = [value]
    return [s for s in value if isinstance(s, str)] if isinstance(value, (list, tuple)) else []


def _text(value, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def describe_file(path: Path, root: Path) -> list[dict]:
    """One entry per Strategy subclass in the file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:                      # syntax errors, null bytes, bad encodings, unreadable files: not a strategy we can list
        return []
    out = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases}
        if "Strategy" not in bases:
            continue
        attrs = {}
        for item in node.body:
            if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
                attrs[item.targets[0].id] = _literal(item.value)
        doc = (ast.get_docstring(node) or ast.get_docstring(tree) or "").strip()
        first = doc.split("\n\n")[0].replace("\n", " ") if doc else ""
        out.append({"path": path.relative_to(root).as_posix(), "name": node.name, "description": first,
                    "universe": _symbols(attrs.get("universe")), "interval": _text(attrs.get("interval"), "1d"),
                    "params": _dict(attrs.get("params")), "param_grid": _dict(attrs.get("param_grid")),
                    "options_on": _symbols(attrs.get("options_on"))})
    return out


def _sidecar(path: Path) -> dict:
    """The user's description, edge and status for a strategy file (strategies/user, strategies/pending), or {}."""
    side = path.with_suffix(".meta.json")
    try:
        return json.loads(side.read_text(encoding="utf-8")) if side.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def list_strategies(root: Path) -> list[dict]:
    """Runnable strategies: the shipped ones and the user's approved ones. Drafts (pending) and removed files are not runnable."""
    folder = root / "strategies"
    if not folder.exists():
        return []
    found = []
    from backtester.web.strategy_store import load_descriptions
    ai = load_descriptions(root)
    for f in sorted(folder.rglob("*.py")):
        if f.name.startswith("_") or "__pycache__" in f.parts or {"pending", "removed"} & set(f.relative_to(folder).parts):
            continue
        for entry in describe_file(f, root):
            meta = _sidecar(f)
            if meta.get("description"):
                entry["description"] = meta["description"]
            entry["edge"] = meta.get("edge", "")
            described = ai.get(entry["path"]) or {}
            entry["ai_description"] = described.get("description", "")
            entry["ai_edge"] = described.get("edge", "")
            entry["ai_risks"] = described.get("risks", [])
            entry["ai_described"] = described.get("described", "")
            entry["source"] = meta.get("source")
            entry["status"] = meta.get("status", "approved" if "user" in f.relative_to(folder).parts else "shipped")
            found.append(entry)
    return found


def list_pending(root: Path) -> list[dict]:
    """Drafts waiting for the user's review (strategies/pending). Never run from here."""
    folder = root / "strategies" / "pending"
    if not folder.exists():
        return []
    out = []
    for f in sorted(folder.glob("*.py")):
        meta = _sidecar(f)
        try:
            code = f.read_text(encoding="utf-8")
        except OSError:
            code = ""
        out.append({"path": f.relative_to(root).as_posix(), "name": f.stem, "description": meta.get("description", ""),
                    "edge": meta.get("edge", ""), "source": meta.get("source"), "created": meta.get("created", ""),
                    "assumptions": meta.get("assumptions", []),
                    "code": code, "universe": [s for e in describe_file(f, root) for s in e["universe"]]})
    return out


def data_needs(strategy: dict, cache: Cache) -> list[dict]:
    """The datasets a strategy needs, and whether each is already cached."""
    needs = [{"symbol": s, "interval": strategy["interval"], "purpose": "prices to trade"} for s in strategy["universe"]]
    for s in strategy["options_on"]:
        idx = VOL_INDEX.get(s.upper())
        if idx:
            needs.append({"symbol": idx, "interval": "1d", "purpose": f"volatility level for {s} options"})
    needs.append({"symbol": RATE, "interval": "1d", "purpose": "interest on cash and margin loans"})
    seen, out = set(), []
    for n in needs:
        key = (n["symbol"], n["interval"])
        if key in seen:
            continue
        seen.add(key)
        meta = cache.meta(n["symbol"], n["interval"]) if cache.has(n["symbol"], n["interval"]) else {}
        out.append({**n, "cached": bool(meta), "first": (meta.get("start") or "")[:10], "last": (meta.get("end") or "")[:10]})
    return out


def suggested_start(strategy: dict, needs: list[dict]) -> str | None:
    """A start date after the history of every price series, with room for indicators to warm up."""
    import pandas as pd
    firsts = [n["first"] for n in needs if n["cached"] and n["purpose"].startswith(("prices", "volatility")) and n["first"]]
    if not firsts:
        return None
    warm = 60 if strategy["options_on"] else 30
    return (pd.Timestamp(max(firsts)) + pd.Timedelta(days=warm)).strftime("%Y-%m-%d")
