"""`caddie notebook-rerun` — re-execute every cell group of an existing
project's notebook, in order, against the connector it was created
with, and report what changed since the last run.

Backs `/caddie-load`: that skill loads the notebook's cells into the
conversation itself (a Claude Code-only step, not something a script
can do); this command only does the re-execution and diff-reporting
half. A notebook is never rewritten here — only its sidecar execution
state (row counts, columns) is updated.
"""

import argparse
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.connectors.loader import load_connector
from caddie.install.identity import resolve_username
from caddie.install.notebooks import resolve_notebooks_root
from caddie.notebook.builder import existing_groups, notebook_path
from caddie.notebook.executor import execute_and_summarize
from caddie.notebook.state import GroupStats, ProjectState, load_state, save_state


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-rerun",
        help="Re-execute an existing project's notebook cell groups and report changes.",
    )
    parser.add_argument("--project", required=True, help="Existing project slug to re-run.")
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
    user_dir = notebooks_root / username
    project_dir = user_dir / args.project

    if not notebook_path(project_dir).is_file():
        raise SystemExit(f"No project '{args.project}' under {user_dir}.")

    print(f"project: {args.project}")
    print(f"notebook: {notebook_path(project_dir)}")

    state = load_state(project_dir)
    if state is None:
        # Pre-existing notebook with no recorded state (e.g. built
        # before this file existed) — fall back to whatever connector
        # is currently active rather than failing outright.
        state = ProjectState(connector=config.connector, connector_settings=config.connector_settings)

    connector = load_connector(state.connector, **state.connector_settings)

    groups = existing_groups(project_dir)
    all_ok = True
    for grp in groups:
        result = execute_and_summarize(connector, grp.code)
        previous = state.groups.get(str(grp.index))

        if result.ok:
            state.groups[str(grp.index)] = GroupStats(
                row_count=result.row_count, columns=result.columns or []
            )
            delta = _format_delta(previous, result.row_count)
            print(f"group {grp.index}: ok rows={result.row_count}{delta} "
                  f"columns={', '.join(result.columns or [])}")
        else:
            all_ok = False
            print(f"group {grp.index}: error: {result.error}")

    save_state(project_dir, state)

    print(f"overall: {'ok' if all_ok else 'partial'}")
    return 0 if all_ok else 1


def _format_delta(previous: GroupStats | None, row_count: int | None) -> str:
    if previous is None or previous.row_count is None or row_count is None:
        return ""
    delta = row_count - previous.row_count
    if delta == 0:
        return " (unchanged)"
    return f" ({'+' if delta > 0 else ''}{delta} vs previous run)"
