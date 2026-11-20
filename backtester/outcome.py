"""Plain-language outcome of a backtest run, for people who will not read a traceback.

Every run ends in exactly one of these kinds:

- ``ok``              the run finished and was saved. Whether the strategy did well is a separate question (see `verdict`).
- ``strategy_error``  the strategy's own code raised an error (a bug in the strategy file).
- ``input_error``     the settings cannot be used (bad dates, no data, unknown parameter, ...). The fix is in the settings.
- ``analysis_error``  the program hit an internal error while completing the run. The strategy's code did not raise it.
- ``stopped``         the run took too long and was stopped (set by the dashboard).

`emit` prints a readable block and one final marker line, ``BT_OUTCOME {json}``, which the dashboard reads.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import asdict, dataclass

MARKER = "BT_OUTCOME "

KINDS = {
    "ok": ("Run completed", None),
    "strategy_error": ("Your strategy stopped with an error", "BT-RUN-001"),
    "input_error": ("The settings cannot be used", "BT-RUN-002"),
    "analysis_error": ("Error completing the analysis", "BT-RUN-003"),
    "stopped": ("The run was stopped", "BT-RUN-004"),
}


@dataclass
class Outcome:
    kind: str
    code: str | None
    title: str
    message: str
    action: str
    line: int | None = None
    source: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def verdict(metrics: dict | None) -> dict | None:
    """Whether the strategy did well in a run that completed. Not a status: a run can complete and still lose money."""
    if not metrics:
        return None
    total = metrics.get("total_return")
    bench = metrics.get("benchmark_total_return")
    trades = metrics.get("trades", 0) or 0
    if total is None:
        return None
    if trades == 0:
        return {"level": "none", "text": "The strategy made no trades, so there is nothing to judge."}
    if total < 0:
        return {"level": "loss", "text": f"The strategy lost money: total return {_pct(total)}."
                + (f" Buy and hold returned {_pct(bench)}." if bench is not None else "")}
    if bench is not None and total < bench:
        return {"level": "lagged", "text": f"The strategy made money ({_pct(total)}) but less than buy and hold ({_pct(bench)})."}
    if bench is not None:
        return {"level": "beat", "text": f"The strategy beat buy and hold: {_pct(total)} against {_pct(bench)}."}
    return {"level": "profit", "text": f"The strategy made money: total return {_pct(total)}."}


def failure(kind: str, message: str, action: str, code: str | None = None, line: int | None = None,
            source: str | None = None) -> Outcome:
    title, default_code = KINDS[kind]
    return Outcome(kind, code or default_code, title, message, action, line, source)


def from_exception(exc: BaseException, strategy_path: str | None) -> Outcome:
    """Classify an exception that stopped a run. The strategy file is checked first: an error raised from its code is the strategy's."""
    from backtester.errors import CodedError
    from backtester.data.yahoo import DataError

    if isinstance(exc, DataError):                       # a subclass of CodedError: checked first for its own advice
        return failure("input_error", str(exc), "Download or import the data it names (Data page, or `bt fetch-yahoo`), then run again.",
                       code=exc.code)
    if isinstance(exc, CodedError):
        return failure("input_error", str(exc), "Change the setting named above and run again.", code=exc.code)

    if strategy_path:
        target = os.path.abspath(strategy_path)
        for fs in reversed(traceback.extract_tb(exc.__traceback__)):
            if os.path.abspath(fs.filename) == target:
                where = f"line {fs.lineno}" + (f": `{(fs.line or '').strip()}`" if fs.line else "")
                return failure(
                    "strategy_error",
                    f"{type(exc).__name__}: {exc} ({os.path.basename(target)}, {where}).",
                    "The error is in the strategy file, so the fix is there. Open the file at that line, correct it, and run again.",
                    line=fs.lineno, source=os.path.basename(target))

    return failure(
        "analysis_error",
        f"{type(exc).__name__}: {exc}. Your strategy's code did not raise this; the program stopped while completing the analysis.",
        "Copy the technical details below and report the code. Your strategy file is not known to be at fault.")


def emit(outcome: Outcome, exit_code: int = 1) -> None:
    """Print the readable summary and the marker line for the dashboard, then exit."""
    print()
    print(f"RESULT: {outcome.title}" + (f" [{outcome.code}]" if outcome.code else ""))
    print(f"  {outcome.message}")
    print(f"  What to do: {outcome.action}")
    print(MARKER + json.dumps(outcome.as_dict()))
    sys.stdout.flush()
    raise SystemExit(exit_code)
