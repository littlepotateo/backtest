"""Background tasks for the dashboard (downloads, imports, checks), kept in memory.

A task runs a function `fn(log)` on a worker thread. `log(text)` adds a line that the page
shows live. Failures never disappear: the error is kept with the task and shown in plain words.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from backtester.data.yahoo import DataError


class Tasks:
    def __init__(self, workers: int = 3):
        self._lock = threading.Lock()
        self._tasks: dict[str, dict] = {}
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="task")

    def submit(self, title: str, fn: Callable[[Callable[[str], None]], dict | None]) -> str:
        task_id = uuid.uuid4().hex[:12]
        task = {"id": task_id, "title": title, "status": "running", "log": [], "result": None, "error": None,
                "started": time.time(), "finished": None}
        with self._lock:
            self._tasks[task_id] = task

        def log(text: str) -> None:
            with self._lock:
                task["log"].append(str(text))

        def run() -> None:
            try:
                result = fn(log)
                with self._lock:
                    task.update(status="done", result=result)
            except DataError as e:                       # an expected, explainable failure: shown as the task's error
                with self._lock:
                    task.update(status="failed", error=str(e), code=e.code)
            except Exception as e:                       # a bug: keep the detail for the log
                log("Unexpected error:\n" + traceback.format_exc(limit=6))
                with self._lock:
                    task.update(status="failed", error=f"Unexpected error: {type(e).__name__}: {e}", code="BT-TASK-500")
            finally:
                with self._lock:
                    task["finished"] = time.time()

        self._pool.submit(run)
        return task_id

    def get(self, task_id: str) -> dict | None:
        with self._lock:
            t = self._tasks.get(task_id)
            return None if t is None else {**t, "log": list(t["log"])}

    def recent(self, limit: int = 12) -> list[dict]:
        with self._lock:
            items = sorted(self._tasks.values(), key=lambda t: t["started"], reverse=True)[:limit]
            return [{**t, "log": list(t["log"])} for t in items]

    def clear_finished(self) -> int:
        with self._lock:
            done = [k for k, t in self._tasks.items() if t["status"] != "running"]
            for k in done:
                del self._tasks[k]
            return len(done)
