"""A small library of research papers and the strategies and runs made from them.

Stored under research/library/: index.json (all papers) and one notes file per paper.
Consensus searches happen in a Claude Code session (the connector is not callable from
Python); the results are saved here so they persist and the dashboard can show them.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from backtester import paths

STATUSES = ("candidate", "replicating", "replicated", "partly replicated", "not replicated", "rejected")


def slug(title: str, year: int | None = None) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48].strip("-")
    return f"{base}-{year}" if year else base


class Library:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or paths.LIBRARY)
        self.index_path = self.root / "index.json"

    def _read(self) -> dict:
        return json.loads(self.index_path.read_text()) if self.index_path.exists() else {"papers": {}}

    def _write(self, data: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(data, indent=2, sort_keys=True))

    def add(self, title: str, *, authors: str = "", year: int | None = None, venue: str = "",
            url: str = "", consensus_id: str = "", finding: str = "", claims: list[str] | None = None,
            full_text: bool = False, abstract: str = "", doi: str = "", openalex_id: str = "") -> str:
        """Save a paper (or update one with the same title and year). `claims` are the
        results the paper reports, quoted as the paper states them; `full_text` says
        whether the claims were read from the full text (otherwise the abstract only)."""
        data = self._read()
        pid = slug(title, year)
        old = data["papers"].get(pid, {})
        data["papers"][pid] = {
            "id": pid, "title": title, "authors": authors or old.get("authors", ""),
            "year": year or old.get("year"), "venue": venue or old.get("venue", ""),
            "url": url or old.get("url", ""), "consensus_id": consensus_id or old.get("consensus_id", ""),
            "finding": finding or old.get("finding", ""),
            "claims": claims if claims is not None else old.get("claims", []),
            "claims_from_full_text": full_text or old.get("claims_from_full_text", False),
            "status": old.get("status", "candidate"), "strategies": old.get("strategies", []),
            "runs": old.get("runs", []), "added": old.get("added", date.today().isoformat()),
            "pdf": old.get("pdf", ""), "text_file": old.get("text_file", ""), "doi": doi or old.get("doi", ""),
            "openalex_id": openalex_id or old.get("openalex_id", ""), "abstract": abstract or old.get("abstract", ""),
        }
        self._write(data)
        notes = self.root / f"{pid}.md"
        if not notes.exists():
            notes.write_text(f"# {title}\n\n{authors} ({year}). {venue}\n\n{url}\n\n## Key finding\n\n{finding}\n\n"
                             "## Rules (as stated)\n\n## Assumptions I had to make\n\n## Replication notes\n")
        return pid

    def attach_pdf(self, pid: str, pdf: bytes, text: str) -> None:
        """Store the PDF and its extracted text beside the library so Claude can read the full text."""
        data = self._read()
        self.get(pid)
        folder = self.root / "files"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{pid}.pdf").write_bytes(pdf)
        (folder / f"{pid}.txt").write_text(text)
        entry = data["papers"][pid]
        entry.update(pdf=f"files/{pid}.pdf", text_file=f"files/{pid}.txt", claims_from_full_text=bool(text.strip()))
        self._write(data)

    def update(self, pid: str, **fields) -> dict:
        """Edit the descriptive fields of a paper (title, authors, year, venue, url, finding, claims, status, ...)."""
        allowed = {"title", "authors", "year", "venue", "url", "finding", "claims", "status", "abstract", "doi",
                   "claims_from_full_text"}
        data = self._read()
        self.get(pid)
        for k, v in fields.items():
            if k not in allowed:
                raise KeyError(f"cannot edit {k!r}")
            if k == "status" and v not in STATUSES:
                raise ValueError(f"status must be one of {STATUSES}")
            if k == "claims":
                v = [c.strip() for c in v if c and c.strip()]
            if k == "year" and v in ("", None):
                v = None
            elif k == "year":
                v = int(v)
            data["papers"][pid][k] = v
        self._write(data)
        return data["papers"][pid]

    def delete(self, pid: str) -> None:
        data = self._read()
        self.get(pid)
        del data["papers"][pid]
        self._write(data)
        for f in (self.root / f"{pid}.md", self.root / "files" / f"{pid}.pdf", self.root / "files" / f"{pid}.txt"):
            f.unlink(missing_ok=True)

    def get(self, pid: str) -> dict:
        papers = self._read()["papers"]
        if pid not in papers:
            raise KeyError(f"no paper {pid!r} in the library")
        return papers[pid]

    def list(self) -> list[dict]:
        return sorted(self._read()["papers"].values(), key=lambda p: (p["status"], p["title"]))

    def set_status(self, pid: str, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        data = self._read()
        self.get(pid)
        data["papers"][pid]["status"] = status
        self._write(data)

    def link_run(self, pid: str, run_dir: str | Path, strategy: str | None = None) -> dict:
        """Attach a finished run to a paper, copying the headline metrics."""
        run_dir = Path(run_dir)
        metrics = json.loads((run_dir / "metrics.json").read_text())
        meta = json.loads((run_dir / "meta.json").read_text())
        data = self._read()
        self.get(pid)
        entry = {"run": str(run_dir), "strategy": strategy or meta.get("strategy"),
                 "period": f"{metrics['start'][:10]} to {metrics['end'][:10]}",
                 "data_source": sorted({d.get("source", "?") for d in meta.get("data", {}).values()}),
                 "metrics": {k: metrics.get(k) for k in ("total_return", "cagr", "volatility", "sharpe",
                                                         "max_drawdown", "trades", "benchmark_total_return",
                                                         "benchmark_max_drawdown")}}
        paper = data["papers"][pid]
        paper["runs"] = [r for r in paper["runs"] if r["run"] != entry["run"]] + [entry]
        if entry["strategy"] and entry["strategy"] not in paper["strategies"]:
            paper["strategies"].append(entry["strategy"])
        if paper["status"] == "candidate":
            paper["status"] = "replicating"
        self._write(data)
        return entry

    def compare(self, pid: str) -> str:
        """Claimed results beside each linked run, as markdown. It lays the numbers out;
        whether the claims hold is a judgement for the reader."""
        p = self.get(pid)
        out = [f"# {p['title']} ({p['year']})", "", f"Status: **{p['status']}**.", ""]
        src = "full text" if p["claims_from_full_text"] else "the abstract only"
        out += [f"## Claimed results (taken from {src})", ""]
        out += [f"- {c}" for c in p["claims"]] or ["- none recorded"]
        if not p["claims_from_full_text"]:
            out += ["", "No numbers are quoted because the full text was not read."]
        out += ["", "## Replication runs", ""]
        if not p["runs"]:
            out.append("None yet.")
        for r in p["runs"]:
            m = r["metrics"]
            out += [f"### {r['strategy']}, {r['period']} (data: {', '.join(r['data_source'])})", "",
                    "| Measure | Replication | Benchmark |", "|---|---|---|",
                    f"| Total return | {m['total_return']:.1%} | {_f(m['benchmark_total_return'])} |",
                    f"| Annual return | {_f(m['cagr'])} | |",
                    f"| Volatility | {_f(m['volatility'])} | |",
                    f"| Sharpe | {m['sharpe']:.2f} | |" if m["sharpe"] is not None else "| Sharpe | n/a | |",
                    f"| Max drawdown | {m['max_drawdown']:.1%} | {_f(m['benchmark_max_drawdown'])} |",
                    f"| Trades | {m['trades']} | |", ""]
        return "\n".join(out)


def _f(x) -> str:
    return "n/a" if x is None else f"{x:.1%}"
