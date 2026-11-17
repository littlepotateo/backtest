"""Re-runs started from the dashboard: `bt validate` in a subprocess, tracked on disk."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from backtester.analysis.findings import ALL_TESTS, CHEAP_TESTS

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PARAM = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=[^\r\n]{1,200}$")
JOB_ID = re.compile(r"^[a-f0-9]{12}$")


class BadRequest(ValueError):
    pass


def _num(value: str, name: str, low: float, high: float) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise BadRequest(f"{name} must be a number")
    if not low <= x <= high:
        raise BadRequest(f"{name} must be between {low:g} and {high:g}")
    return str(int(x)) if x == int(x) and name in ("paths", "synthetic") else str(x)


class Jobs:
    def __init__(self, root: Path, runs_dir: Path, cache_dir: Path):
        self.root, self.runs_dir, self.cache_dir = root.resolve(), runs_dir, cache_dir
        self.dir = runs_dir / "_jobs"
        self.procs: dict[str, subprocess.Popen] = {}

    def command(self, form: dict) -> list[str]:
        """Validated argument list; nothing from the form reaches a shell."""
        strategy = (self.root / form.get("strategy", "")).resolve()
        if strategy.suffix != ".py" or not strategy.is_file() or (self.root / "strategies").resolve() not in strategy.parents:
            raise BadRequest("the strategy must be a .py file under strategies/")
        cmd = [sys.executable, "-m", "backtester.cli", "--cache", str(self.cache_dir), "validate",
               str(strategy.relative_to(self.root)), "--out", str(self.runs_dir)]
        for key, flag in (("start", "--start"), ("end", "--end")):
            v = (form.get(key) or "").strip()
            if v:
                if not DATE.match(v):
                    raise BadRequest(f"{key} must be a date like 2020-01-31")
                cmd += [flag, v]
        cmd += ["--cash", _num(form.get("cash") or "100000", "cash", 1_000, 1e10)]
        cmd += ["--cost-multiplier", _num(form.get("cost_multiplier") or "1", "cost multiplier", 0, 20)]
        cmd += ["--risk-free", _num(form.get("risk_free") or "0", "risk-free rate", -0.05, 0.5)]
        cmd += ["--paths", _num(form.get("paths") or "2000", "paths", 100, 20000)]
        if (form.get("synthetic") or "0") not in ("", "0"):
            cmd += ["--synthetic", _num(form["synthetic"], "synthetic", 1, 500)]
        bench = (form.get("benchmark") or "").strip()
        if bench:
            if not re.match(r"^[A-Za-z0-9^.-]{1,12}$", bench):
                raise BadRequest("benchmark must be a symbol")
            cmd += ["--benchmark", bench]
        for line in (form.get("params") or "").splitlines():
            line = line.strip()
            if line:
                if not PARAM.match(line):
                    raise BadRequest(f"parameter {line!r} must look like name=value")
                cmd += ["--param", line]
        tests = [t for t in form.get("tests", []) if t in ALL_TESTS]
        if form.get("tests") is not None and not tests:
            raise BadRequest("choose at least one test")
        cmd += ["--tests", ",".join(tests or CHEAP_TESTS)]
        return cmd

    def start(self, form: dict) -> str:
        cmd = self.command(form)
        self.dir.mkdir(parents=True, exist_ok=True)
        job_id = uuid.uuid4().hex[:12]
        out = self.dir / f"{job_id}.log"
        proc = subprocess.Popen(cmd, cwd=self.root, stdout=out.open("w", encoding="utf-8"), stderr=subprocess.STDOUT,
                                env={**os.environ, "PYTHONUTF8": "1"})
        self.procs[job_id] = proc
        self._save(job_id, {"id": job_id, "started": time.time(), "cmd": cmd[3:], "status": "running",
                            "strategy": form.get("strategy"), "pid": proc.pid})
        return job_id

    def _save(self, job_id: str, data: dict) -> None:
        (self.dir / f"{job_id}.json").write_text(json.dumps(data), encoding="utf-8")

    def status(self, job_id: str) -> dict:
        if not JOB_ID.match(job_id) or not (self.dir / f"{job_id}.json").exists():
            raise BadRequest("no such job")
        job = json.loads((self.dir / f"{job_id}.json").read_text(encoding="utf-8"))
        log = (self.dir / f"{job_id}.log")
        text = log.read_text(encoding="utf-8") if log.exists() else ""
        proc = self.procs.get(job_id)
        if job["status"] == "running":
            code = proc.poll() if proc else (None if (time.time() - job["started"]) < 1800 else -1)
            if code is not None:
                m = re.search(r"Saved to runs/([^\s]+)", text) or re.search(r"Saved to \S*/([^/\s]+)", text)
                job.update(status="done" if code == 0 and m else "failed", exit_code=code,
                           run_id=m.group(1) if m else None)
                self._save(job_id, job)
        job["output"] = text[-6000:]
        return job
