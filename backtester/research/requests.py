"""Paper-search requests made from the dashboard for Claude Code to carry out.

The Consensus connector can only be called by Claude in a Claude Code session, not by this
program. So the dashboard saves what the user wants searched as a small file under
research/library/requests/, the user pastes one line of instruction into Claude Code, Claude
runs the Consensus search and saves the papers into the library, and the dashboard shows
the result after a refresh.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from pathlib import Path

from backtester.errors import CodedError

REQUEST_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-f0-9]{4}$")
MAX_QUERY = 300


class RequestError(CodedError):
    """A search request was not valid."""
    code = "BT-REQ-000"


def instruction(req: dict) -> str:
    """The one line the user pastes into Claude Code."""
    note = f" Extra guidance: {req['notes'].rstrip('.')}." if req.get("notes") else ""
    return (f"Use the backtest skill to carry out paper-search request {req['id']} "
            f"(saved in research/library/requests/{req['id']}.json): search Consensus for \"{req['query']}\".{note} "
            f"Save the best 3 to 6 papers with bt paper add --request {req['id']} ..., "
            f"then finish with bt paper request-done {req['id']} --summary \"...\".")


class Requests:
    def __init__(self, library_root: str | Path):
        self.root = Path(library_root) / "requests"

    def _path(self, rid: str) -> Path:
        if not REQUEST_ID.match(rid or ""):
            raise KeyError(f"no request {rid!r}")
        return self.root / f"{rid}.json"

    def _save(self, req: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(req["id"]).write_text(json.dumps(req, indent=2, sort_keys=True), encoding="utf-8")

    def create(self, query: str, notes: str = "") -> dict:
        query, notes = " ".join((query or "").split()), " ".join((notes or "").split())
        if len(query) < 3:
            raise RequestError("Describe what to search for, for example “momentum strategies for ETFs”.", "BT-REQ-001")
        if len(query) > MAX_QUERY or len(notes) > 1000:
            raise RequestError(f"Keep the search to {MAX_QUERY} characters and the guidance to 1000.", "BT-REQ-002")
        now = datetime.now()
        req = {"id": f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}", "query": query, "notes": notes,
               "status": "pending", "created": now.isoformat(timespec="seconds"), "papers": [], "summary": "", "done": None}
        self._save(req)
        return {**req, "instruction": instruction(req)}

    def get(self, rid: str) -> dict:
        path = self._path(rid)
        if not path.exists():
            raise KeyError(f"no request {rid!r}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self) -> list[dict]:
        if not self.root.exists():
            return []
        reqs = []
        for p in self.root.glob("*.json"):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue                   # a half-written or damaged request file is skipped
            if isinstance(r, dict) and REQUEST_ID.match(str(r.get("id", ""))) and r.get("query"):
                reqs.append({"notes": "", "status": "pending", "papers": [], "summary": "", "created": "", "done": None, **r})
        return sorted(reqs, key=lambda r: r["id"], reverse=True)

    def pending(self) -> list[dict]:
        return [r for r in self.list() if r["status"] == "pending"]

    def attach_paper(self, rid: str, pid: str) -> None:
        req = self.get(rid)
        if pid not in req["papers"]:
            req["papers"].append(pid)
        self._save(req)

    def complete(self, rid: str, summary: str = "") -> dict:
        req = self.get(rid)
        req.update(status="done", summary=summary.strip(), done=datetime.now().isoformat(timespec="seconds"))
        self._save(req)
        return req

    def delete(self, rid: str) -> None:
        path = self._path(rid)
        if not path.exists():
            raise KeyError(f"no request {rid!r}")
        path.unlink()
