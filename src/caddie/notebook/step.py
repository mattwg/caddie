"""`caddie notebook-step` - append and execute one exploratory step
(query or chart) in an already-planned episode. Repeatable: this is
what lets Claude iterate toward a real answer instead of running
exactly one query per `/caddie-ask` call.
"""

import argparse
import sys
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.connectors.loader import load_connector
from caddie.install.identity import resolve_username
from caddie.install.notebooks import resolve_notebooks_root
from caddie.notebook.builder import (
    EpisodeNotFoundError,
    PlanRequiredError,
    append_step,
    existing_episodes,
    notebook_path,
)
from caddie.notebook.executor import DEFAULT_PREVIEW_ROWS, execute_and_summarize, execute_chart
from caddie.notebook.state import ProjectState, StepStats, load_state, save_state


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-step",
        help="Append and execute one query or chart step in a planned episode.",
    )
    parser.add_argument("--project", required=True, help="Existing project slug.")
    parser.add_argument("--episode", required=True, type=int, help="Episode number within the project.")
    parser.add_argument("--kind", choices=["query", "chart"], default="query")
    parser.add_argument(
        "--label",
        help="Short description prepended as a comment, for readability in marimo edit.",
    )
    parser.add_argument(
        "--preview-rows",
        type=int,
        default=DEFAULT_PREVIEW_ROWS,
        help=f"How many rows to preview if the result is larger (default {DEFAULT_PREVIEW_ROWS}).",
    )
    parser.add_argument(
        "--code-file",
        help="File containing the code (SQL/Python for a query, Plotly Python for a chart). "
        "Defaults to stdin.",
    )
    parser.add_argument(
        "--config-path",
        help="Override the caddie.yaml path (mainly for testing).",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path) if args.config_path else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    username = config.username or resolve_username()
    notebooks_root = (
        Path(config.notebooks_root).expanduser()
        if config.notebooks_root
        else resolve_notebooks_root(None)
    )
    project_dir = notebooks_root / username / args.project
    code = Path(args.code_file).read_text() if args.code_file else sys.stdin.read()

    print(f"project: {args.project}")

    try:
        step = append_step(project_dir, args.episode, code, kind=args.kind, label=args.label)
    except (EpisodeNotFoundError, PlanRequiredError) as exc:
        print("status: error")
        print(f"error: {exc}")
        return 1

    print(f"notebook: {notebook_path(project_dir)}")
    print(f"episode: {args.episode}")
    print(f"step: {step}")

    state = load_state(project_dir) or ProjectState(
        connector=config.connector, connector_settings=config.connector_settings
    )
    connector = load_connector(state.connector, **state.connector_settings)

    if args.kind == "query":
        return _run_query_step(project_dir, state, args.episode, step, connector, code, args.preview_rows)
    return _run_chart_step(project_dir, state, args.episode, step, connector, code)


def _run_query_step(project_dir, state, episode, step, connector, code, preview_rows) -> int:
    result = execute_and_summarize(connector, code, preview_rows=preview_rows)
    if not result.ok:
        print("status: error")
        print(f"error: {result.error}")
        return 1

    state.steps[f"{episode}_{step}"] = StepStats(
        kind="query", row_count=result.row_count, columns=result.columns or []
    )
    save_state(project_dir, state)

    print("status: ok")
    print(f"rows: {result.row_count}")
    print(f"columns: {', '.join(result.columns or [])}")
    print(f"preview:\n{result.preview}")
    return 0


def _run_chart_step(project_dir, state, episode, step, connector, code) -> int:
    prior_steps = [
        s
        for e in existing_episodes(project_dir)
        if e.index == episode
        for s in e.steps
        if s.step < step
    ]
    chart_var = f"chart_{episode}_{step}"
    result = execute_chart(connector, prior_steps, code, chart_var)
    if not result.ok:
        print("status: error")
        print(f"error: {result.error}")
        return 1

    state.steps[f"{episode}_{step}"] = StepStats(kind="chart")
    save_state(project_dir, state)

    print("status: ok")
    print(f"chart: {result.description}")
    return 0
