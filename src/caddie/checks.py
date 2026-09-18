"""Shared pass/fail check running and summary printing.

Both `caddie install` and `caddie update` end with a plain pass/fail
summary rather than each hand-rolling their own reporting. A check is
just a label and an action; failures are captured per-check rather
than aborting the whole run, so one failing step (e.g. connector auth)
doesn't hide the pass/fail state of the others.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass
class CheckResult:
    label: str
    ok: bool
    detail: str | None = None


def run_checks(checks: list[tuple[str, Callable[[], None]]]) -> list[CheckResult]:
    results = []
    for label, action in checks:
        try:
            action()
        except Exception as exc:
            results.append(CheckResult(label, False, str(exc)))
        else:
            results.append(CheckResult(label, True))
    return results


def print_summary(results: list[CheckResult]) -> bool:
    for result in results:
        status = "pass" if result.ok else "fail"
        line = f"[{status}] {result.label}"
        if result.detail:
            line += f": {result.detail}"
        print(line)
    return all(result.ok for result in results)
