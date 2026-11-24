"""Adding, removing and reviewing strategy files from the dashboard.

Layout under the project's `strategies/` folder:

- `strategies/` (top level, examples and replications): shipped, not touched here.
- `strategies/user/`: strategies the user uploaded or approved. Listed and runnable.
- `strategies/pending/`: drafts (for example reconstructed from a paper). Listed for review only; never run until approved.
- `strategies/removed/`: removed strategies, kept so a removal can be undone by hand.

Every added strategy has a sidecar `<name>.meta.json` with the description, edge, source and status.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from backtester.errors import CodedError

NAME = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
MAX_BYTES = 200_000
DRY_RUN_SECONDS = 180
FOLDERS = ("user", "pending", "removed")


def _strategies_dir(root: Path) -> Path:
    return root / "strategies"


def check_source(source: str) -> str:
    """Static checks on an uploaded or drafted strategy. Returns the Strategy class name, or raises CodedError (BT-RUN-002)."""
    if len(source.encode("utf-8")) > MAX_BYTES:
        raise CodedError(f"The file is larger than {MAX_BYTES // 1000} KB. Strategy files are a few kilobytes.", "BT-RUN-002")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise CodedError(f"The file has a Python syntax error at line {e.lineno}: {e.msg}.", "BT-RUN-002")
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)
               and any((b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")) == "Strategy" for b in n.bases)]
    if len(classes) != 1:
        raise CodedError(f"The file must define exactly one class that inherits from Strategy (found {len(classes)}).", "BT-RUN-002")
    cls = classes[0]
    attrs = {}
    for item in cls.body:
        if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
            attrs[item.targets[0].id] = item.value
    for required in ("universe", "interval"):
        if required not in attrs:
            raise CodedError(f"The strategy class must set `{required}` (for example universe = [\"SPY\"]).", "BT-RUN-002")
    for literal in ("universe", "interval", "params", "param_grid"):
        if literal in attrs:
            try:
                ast.literal_eval(attrs[literal])
            except ValueError:
                raise CodedError(f"`{literal}` must be a plain value (a list, a number or a string), not an expression.", "BT-RUN-002")
    return cls.name


def dry_run(path: Path, root: Path, cache_dir: Path) -> dict:
    """Run `bt check` on the file in a subprocess. Returns {"ok": bool, "warning": str|None}; raises CodedError when the code is at fault."""
    cmd = [sys.executable, "-m", "backtester.cli", "--cache", str(cache_dir), "check", str(path)]
    env = {**os.environ, "PYTHONUTF8": "1"}
    try:
        done = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=DRY_RUN_SECONDS, env=env)
    except subprocess.TimeoutExpired:
        raise CodedError(f"The check did not finish within {DRY_RUN_SECONDS} seconds, so the file was not added. "
                         "A strategy that loops forever on the first bar is the usual cause.", "BT-RUN-001")
    text = (done.stdout or "") + (done.stderr or "")
    if done.returncode == 0:
        return {"ok": True, "warning": None}
    marker = next((ln for ln in text.splitlines() if ln.startswith("BT_OUTCOME ")), None)
    if marker:
        out = json.loads(marker[len("BT_OUTCOME "):])
        if out.get("kind") == "strategy_error":
            raise CodedError(f"The strategy raised an error when run: {out.get('message', '')}", "BT-RUN-001")
        msg = out.get("message", "").lower()
        if out.get("kind") == "input_error" and any(w in msg for w in ("no cached", "no data", "not cached", "download")):
            return {"ok": True, "warning": "The file was checked for syntax and structure only: the price data it needs is not downloaded yet, so it could not be run."}
        if out.get("kind") == "input_error":
            raise CodedError(f"The strategy's settings cannot be used: {out.get('message', '')}", out.get("code") or "BT-RUN-002")
    raise CodedError("The check of this file failed for a reason the program could not classify. The technical log is in the terminal.", "BT-RUN-003")


def _safe_rel(root: Path, rel: str, folders: tuple[str, ...]) -> Path:
    """A path under strategies/<folder>/ only; anything else is refused."""
    base = _strategies_dir(root).resolve()
    p = (root / rel).resolve()
    if p.suffix != ".py" or not any(p.parent == (base / f).resolve() for f in folders):
        raise CodedError("That strategy cannot be changed here.", "BT-RUN-002")
    if not p.is_file():
        raise CodedError("That strategy file no longer exists.", "BT-RUN-002")
    return p


def add(root: Path, cache_dir: Path, name: str, source: str, *, status: str, description: str = "", edge: str = "",
        source_ref: str | None = None, trusted: bool = False) -> dict:
    """Validate and store a strategy file. status is 'approved' (strategies/user) or 'pending' (strategies/pending)."""
    if status not in ("approved", "pending"):
        raise CodedError("Unknown status.", "BT-RUN-002")
    if not trusted:
        raise CodedError("Tick the box to confirm you trust this code: it runs on this computer with your permissions.", "BT-RUN-002")
    name = (name or "").strip().lower()
    if not NAME.match(name):
        raise CodedError("The name must be 3 to 41 letters, digits or underscores, starting with a letter (for example qqq_trend).", "BT-RUN-002")
    folder = _strategies_dir(root) / ("user" if status == "approved" else "pending")
    target = folder / f"{name}.py"
    if any(_strategies_dir(root).rglob(f"{name}.py")):      # any folder: a name must identify one file
        raise CodedError(f"A strategy called {name} already exists. Choose another name.", "BT-RUN-002")
    class_name = check_source(source)
    folder.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    warning = None
    try:
        result = dry_run(target, root, cache_dir)
        warning = result["warning"]
    except CodedError:
        target.unlink(missing_ok=True)
        raise
    meta = {"class": class_name, "description": description.strip()[:600], "edge": edge.strip()[:600],
            "source": source_ref, "status": status, "created": dt.date.today().isoformat(), "returns": "total"}
    target.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"path": target.relative_to(root).as_posix(), "class": class_name, "status": status, "warning": warning}


def remove(root: Path, rel: str) -> str:
    """Move a user or pending strategy (and its sidecar) to strategies/removed/. Reversible by moving the files back."""
    p = _safe_rel(root, rel, ("user", "pending"))
    removed = _strategies_dir(root) / "removed"
    removed.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = removed / f"{p.stem}-{stamp}.py"
    shutil.move(str(p), dest)
    side = p.with_suffix(".meta.json")
    if side.exists():
        shutil.move(str(side), dest.with_suffix(".meta.json"))
    return dest.relative_to(root).as_posix()


def approve(root: Path, rel: str) -> str:
    """Move a pending draft to strategies/user/. Nothing is run."""
    p = _safe_rel(root, rel, ("pending",))
    target = _strategies_dir(root) / "user" / p.name
    if target.exists():
        raise CodedError(f"A strategy called {p.stem} is already in your strategies. Remove it first, or rename this draft.", "BT-RUN-002")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), target)
    side = p.with_suffix(".meta.json")
    if side.exists():
        meta = json.loads(side.read_text(encoding="utf-8"))
        meta["status"] = "approved"
        shutil.move(str(side), target.with_suffix(".meta.json"))
        target.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return target.relative_to(root).as_posix()


def reject(root: Path, rel: str) -> None:
    """Delete a pending draft and its sidecar (after the user confirmed)."""
    p = _safe_rel(root, rel, ("pending",))
    p.unlink()
    p.with_suffix(".meta.json").unlink(missing_ok=True)
