"""Runs a step's code against the connector and reduces the result to
something Claude can actually reason with.

For a query step, that's the true row count (used for `/caddie-load`
diffing) plus an adaptive preview: every row if the result is small,
otherwise a capped sample with a note on how many more exist. The
preview is bandwidth for Claude's own reasoning while it decides
whether to continue, add a chart, revise the plan, or conclude - the
notebook's own `result_{E}_{S}` is always the full, uncapped result
when the file is opened in `marimo edit`, regardless of preview size.
Aggregation/filtering belongs in the SQL itself; the preview is not
how a real answer's data volume should be handled.

For a chart step, there's no query result to summarize - instead the
Claude-authored chart code is validated for real, the same "catch it
before claiming success" way a query is: replay the episode's earlier
queries to rebuild their `result_{E}_{S}` bindings, exec the chart code
against that plus `plotly.express`/the shared template, and check it
actually produced a Plotly figure.
"""

from dataclasses import dataclass
from typing import Any

DEFAULT_PREVIEW_ROWS = 50
MAX_PREVIEW_ROWS = 500
MAX_PREVIEW_CHARS = 8000


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    row_count: int | None = None
    columns: list[str] | None = None
    preview: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ChartResult:
    ok: bool
    description: str | None = None
    error: str | None = None


def execute_and_summarize(
    connector: Any, code: str, preview_rows: int = DEFAULT_PREVIEW_ROWS
) -> ExecutionResult:
    preview_rows = max(1, min(preview_rows, MAX_PREVIEW_ROWS))
    try:
        result = connector.execute(code)
        columns = list(getattr(result, "columns", None) or [])
        row_count = _row_count(result)
        rows = _preview_rows(result, preview_rows)
        if not columns and rows:
            columns = _columns_from_rows(rows)
        preview = _render_preview(rows, columns, row_count)
    except Exception as exc:
        return ExecutionResult(ok=False, error=str(exc))

    return ExecutionResult(ok=True, row_count=row_count, columns=columns, preview=preview)


def execute_chart(
    connector: Any, prior_steps: list[Any], chart_code: str, chart_var: str
) -> ChartResult:
    """`prior_steps` is that episode's `NotebookStep`s so far (query and
    chart alike; chart ones are skipped). Each query step's code is
    re-run to rebuild its `result_{E}_{S}` binding - this executor has
    no cross-process cache, so a chart added right after its query does
    re-run it once more."""
    try:
        import plotly.express as px
        from plotly.graph_objects import Figure

        from caddie.charting import template as _caddie_template

        namespace: dict[str, Any] = {"px": px, "_caddie_template": _caddie_template}
        for step in prior_steps:
            if step.kind != "query":
                continue
            prefix = f"{step.episode}_{step.step}"
            namespace[f"query_{prefix}"] = step.code
            namespace[f"result_{prefix}"] = connector.execute(step.code)

        exec(chart_code, namespace)  # noqa: S102 - Claude-authored analysis code, same trust level as an executed query
        fig = namespace.get(chart_var)
    except Exception as exc:
        return ChartResult(ok=False, error=str(exc))

    if not isinstance(fig, Figure):
        return ChartResult(ok=False, error=f"{chart_var} was not assigned a Plotly Figure.")

    return ChartResult(ok=True, description=_describe_figure(fig))


def _describe_figure(fig: Any) -> str:
    trace_types = sorted({trace.type for trace in fig.data}) if fig.data else []
    title = fig.layout.title.text if fig.layout and fig.layout.title else None
    parts = [f"{len(fig.data)} trace(s)"]
    if trace_types:
        parts.append("type=" + ",".join(trace_types))
    if title:
        parts.append(f"title={title!r}")
    return ", ".join(parts)


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


def _preview_rows(result: Any, n: int) -> list[dict] | None:
    limit = getattr(result, "limit", None)
    if callable(limit) and hasattr(result, "columns"):
        try:
            collected = result.limit(n).collect()
        except Exception:
            return None
        return [row.asDict() if hasattr(row, "asDict") else dict(row) for row in collected]
    try:
        subset = result[:n]
    except TypeError:
        return None
    return subset if isinstance(subset, list) else None


def _columns_from_rows(rows: list[dict]) -> list[str]:
    return list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []


def _render_preview(
    rows: list[dict] | None, columns: list[str], total_rows: int | None
) -> str | None:
    if rows is None:
        return None
    if not rows:
        return "(no rows)"

    cols = columns or _columns_from_rows(rows)
    lines = [" | ".join(cols)]
    lines += [" | ".join(str(row.get(c, "")) for c in cols) for row in rows]
    text = "\n".join(lines)

    if total_rows is not None and total_rows > len(rows):
        text += (
            f"\n... {len(rows)} of {total_rows} rows shown; refine the query "
            f"(aggregate/filter) or pass --preview-rows to see more "
            f"(up to {MAX_PREVIEW_ROWS})."
        )

    if len(text) > MAX_PREVIEW_CHARS:
        text = text[:MAX_PREVIEW_CHARS] + "\n… (truncated)"
    return text
