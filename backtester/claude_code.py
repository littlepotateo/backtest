"""Calling Claude Code from the dashboard.

Claude Code is the AI engine of this project (no API key). When the `claude` program is installed on this
computer and signed in, the dashboard runs it in the background (`claude -p`, the prompt on standard input) and
shows its progress. Claude is given only what the job needs (read the saved text of one paper, or search
Consensus) and no shell, no file writing: it answers with a JSON object, and this program validates the object
and saves it. Whatever the paper's text says, it cannot make Claude change anything on the computer.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from backtester.errors import CodedError


class ClaudeError(CodedError):
    """Claude Code could not be run, or its answer could not be used."""
    code = "BT-CLAUDE-000"


INSTALL_HELP = ("Install Claude Code on this computer and sign in once by typing `claude` in a terminal "
                "(instructions: https://code.claude.com/docs), then restart the dashboard.")

_procs: set[subprocess.Popen] = set()
_lock = threading.Lock()
_slots = threading.Semaphore(2)               # at most two Claude jobs at a time
DEFAULT_TIMEOUT = 600                         # seconds


def _stop_all() -> None:
    with _lock:
        for p in list(_procs):
            try:
                p.kill()
            except OSError:
                pass


atexit.register(_stop_all)


def find_claude() -> str | None:
    """The `claude` program: BACKTEST_CLAUDE if set, else on the PATH, else the usual install folders."""
    override = os.environ.get("BACKTEST_CLAUDE")
    if override:
        return override if Path(override).exists() else None
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    for c in (home / ".local" / "bin" / "claude.exe", home / ".local" / "bin" / "claude", home / ".claude" / "local" / "claude",
              Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd"):
        if c.name and c.exists():
            return str(c)
    return None


def status() -> dict:
    exe = find_claude()
    return {"available": bool(exe), "path": exe or "", "help": "" if exe else INSTALL_HELP}


def extract_json(text: str) -> dict:
    """The JSON object in Claude's reply (it may be wrapped in a code fence or a sentence)."""
    text = (text or "").strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except ValueError:
        pass
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                esc = (ch == "\\") and not esc
                if ch == '"' and not esc:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start:i + 1])
                        if isinstance(value, dict):
                            return value
                    except ValueError:
                        pass
                    break
        start = text.find("{", start + 1)
    raise ClaudeError("Claude's reply was not in the expected form (a JSON object), so nothing was saved. "
                      f"The start of the reply was: {text[:200]!r}. Try again.", "BT-CLAUDE-005")


def _describe(block: dict) -> str | None:
    if block.get("type") != "tool_use":
        return None
    name, args = str(block.get("name", "")), block.get("input") or {}
    if "consensus" in name.lower():
        return f"Searching Consensus for: {args.get('query', '')}"[:200]
    if name == "Read":
        return "Reading the saved text of the paper"
    if name == "ToolSearch":
        return "Looking for the search tool"
    return f"Using {name}"


def run_claude(prompt: str, *, allowed_tools: list[str], cwd: Path, log: Callable[[str], None] = lambda s: None,
               timeout: float | None = None, max_turns: int = 25) -> dict:
    """Run one headless Claude Code turn and return {"text": final reply, "denied": [tool names it was not allowed to use]}."""
    timeout = timeout or DEFAULT_TIMEOUT
    exe = find_claude()
    if not exe:
        raise ClaudeError("Claude Code was not found on this computer. " + INSTALL_HELP, "BT-CLAUDE-001")
    cmd = [exe, "-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence", "--permission-mode", "dontAsk",
           "--max-turns", str(max_turns), "--allowedTools", *allowed_tools]
    with _slots:
        log("Starting Claude Code (this can take a minute or two)…")
        try:
            proc = subprocess.Popen(cmd, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONUTF8": "1"})
        except OSError as e:
            raise ClaudeError(f"Claude Code could not be started ({type(e).__name__}: {e}). " + INSTALL_HELP, "BT-CLAUDE-002")
        with _lock:
            _procs.add(proc)
        timed_out = threading.Event()

        def kill() -> None:
            timed_out.set()
            try:
                proc.kill()
            except OSError:
                pass
        timer = threading.Timer(timeout, kill)
        timer.start()
        err_lines: list[str] = []
        threading.Thread(target=lambda: err_lines.extend(proc.stderr), daemon=True).start()
        result, text_parts = None, []
        try:
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except OSError:
                pass
            for line in proc.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                kind = ev.get("type")
                if kind == "assistant":
                    for block in (ev.get("message") or {}).get("content") or []:
                        if block.get("type") == "text" and block.get("text", "").strip():
                            text_parts.append(block["text"])
                        said = _describe(block)
                        if said:
                            log(said)
                elif kind == "result":
                    result = ev
            proc.wait()
        finally:
            timer.cancel()
            with _lock:
                _procs.discard(proc)
    if timed_out.is_set():
        raise ClaudeError(f"Claude Code did not finish within {max(1, round(timeout / 60))} minute(s) and was stopped. Try again, or use a shorter paper.", "BT-CLAUDE-002")
    stderr = "".join(err_lines).strip()[-400:]
    if result is None:
        raise ClaudeError(f"Claude Code stopped without an answer (exit code {proc.returncode}). {stderr}".strip(), "BT-CLAUDE-002")
    denied = [str(d.get("tool_name", "")) for d in (result.get("permission_denials") or []) if isinstance(d, dict)]
    reply = str(result.get("result") or "")
    if result.get("is_error"):
        low = reply.lower()
        if "login" in low or "log in" in low or "api key" in low or "authenticat" in low or "not signed" in low:
            raise ClaudeError("Claude Code is installed but not signed in. Type `claude` in a terminal, sign in, then try again. "
                              f"(It said: {reply[:160]})", "BT-CLAUDE-003")
        raise ClaudeError(f"Claude Code reported an error: {reply[:300] or result.get('subtype', 'unknown')}", "BT-CLAUDE-002")
    for d in denied:
        log(f"Claude tried to use {d}, which is not allowed in this job, so it was blocked.")
    return {"text": reply or "\n".join(text_parts), "denied": denied, "seconds": round(float(result.get("duration_ms") or 0) / 1000, 1)}
