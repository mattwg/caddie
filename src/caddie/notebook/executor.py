"""Runs a skill's generated code against the connector and reduces the
result to a compact summary — row count and column names, never
full row-level output.

This is what actually catches a broken query (bad table name, etc.)
before `/caddie-ask` reports success in chat. The notebook's code cell
runs the same `connector.execute(code)` call lazily whenever the file
is reopened in `marimo edit`, so running it here once, eagerly, also
doubles as proof the notebook will render real output rather than an
error the next time it's opened.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    row_count: int | None = None
    columns: list[str] | None = None
    error: str | None = None


def execute_and_summarize(connector: Any, code: str) -> ExecutionResult:
    try:
        result = connector.execute(code)
        columns = list(getattr(result, "columns", None) or [])
        row_count = _row_count(result)
        if not columns and row_count:
            columns = _columns_from_rows(result)
    except Exception as exc:
        return ExecutionResult(ok=False, error=str(exc))

    return ExecutionResult(ok=True, row_count=row_count, columns=columns)


def _row_count(result: Any) -> int | None:
    # A DataFrame-like result (e.g. a Spark DataFrame) exposes both
    # `.columns` and a zero-arg `.count()`. Check for `.columns` first
    # so a plain list's unrelated `.count(value)` method isn't mistaken
    # for it.
    if hasattr(result, "columns"):
        count = getattr(result, "count", None)
        if callable(count):
            return count()
    try:
        return len(result)
    except TypeError:
        return None


def _columns_from_rows(result: Any) -> list[str]:
    try:
        first = result[0]
    except (TypeError, IndexError, KeyError):
        return []
    return list(first.keys()) if isinstance(first, dict) else []
