"""Finding strategy files and reading their settings without running them (static parsing)."""

from __future__ import annotations

import ast
from pathlib import Path

from backtester.data.cache import Cache
from backtester.options.surface import VOL_INDEX

RATE = "^IRX"


def _literal(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def describe_file(path: Path, root: Path) -> list[dict]:
    """One entry per Strategy subclass in the file."""
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, OSError, UnicodeDecodeError):
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
                    "universe": attrs.get("universe") or [], "interval": attrs.get("interval") or "1d",
                    "params": attrs.get("params") or {}, "param_grid": attrs.get("param_grid") or {},
                    "options_on": attrs.get("options_on") or []})
    return out


def list_strategies(root: Path) -> list[dict]:
    folder = root / "strategies"
    if not folder.exists():
        return []
    found = []
    for f in sorted(folder.rglob("*.py")):
        if f.name.startswith("_") or "__pycache__" in f.parts:
            continue
        found.extend(describe_file(f, root))
    return found


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
