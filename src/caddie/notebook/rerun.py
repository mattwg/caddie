"""`caddie notebook-rerun` - re-execute every episode's steps, in
order, against the connector the project was created with, then
re-render the notebook so a reloaded project's click-to-open link
reflects the latest data.

Backs `/caddie-load`: that skill loads the notebook's cells into the
conversation itself (a Claude Code-only step, not something a script
can do); this command only does the re-execution, diff-reporting, and
re-render. The notebook's own cells are never rewritten here - only its
sidecar execution state and its rendered HTML export are.
"""

import argparse
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.connectors.loader import load_connector
from caddie.install.identity import resolve_username
from caddie.install.notebooks import resolve_notebooks_root
from caddie.notebook.builder import NotebookEpisode, existing_episodes, notebook_path
from caddie.notebook.executor import execute_and_summarize, execute_chart
from caddie.notebook.render import RenderError, render_notebook
from caddie.notebook.state import ProjectState, StepStats, load_state, save_state


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-rerun",
        help="Re-execute an existing project's notebook and report changes.",
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

    state = load_state(project_dir) or ProjectState(
        connector=config.connector, connector_settings=config.connector_settings
    )
    connector = load_connector(state.connector, **state.connector_settings)

    all_ok = True
    for episode in existing_episodes(project_dir):
        all_ok &= _rerun_episode(episode, connector, state)

    save_state(project_dir, state)

    try:
        rendered = render_notebook(project_dir)
        print(f"rendered: {rendered}")
        print(f"open: file://{rendered}")
    except RenderError as exc:
        print(f"render: error: {exc}")
        all_ok = False

    print(f"overall: {'ok' if all_ok else 'partial'}")
    return 0 if all_ok else 1


def _rerun_episode(episode: NotebookEpisode, connector, state: ProjectState) -> bool:
    ok = True
    steps_so_far = []

    for s in episode.steps:
        key = f"{episode.index}_{s.step}"
        previous = state.steps.get(key)

        if s.kind == "query":
            result = execute_and_summarize(connector, s.code)
            if result.ok:
                state.steps[key] = StepStats(
                    kind="query", row_count=result.row_count, columns=result.columns or []
                )
                delta = _format_delta(previous, result.row_count)
                print(f"episode {episode.index} step {s.step} (query): ok rows={result.row_count}{delta}")
            else:
                ok = False
                print(f"episode {episode.index} step {s.step} (query): error: {result.error}")
        else:
            chart_var = f"chart_{episode.index}_{s.step}"
            chart_result = execute_chart(connector, steps_so_far, s.code, chart_var)
            if chart_result.ok:
                state.steps[key] = StepStats(kind="chart")
                print(f"episode {episode.index} step {s.step} (chart): ok {chart_result.description}")
            else:
                ok = False
                print(f"episode {episode.index} step {s.step} (chart): error: {chart_result.error}")

        steps_so_far.append(s)

    print(f"episode {episode.index} plan: {episode.plan or 'none recorded'}")
    print(f"episode {episode.index} answer: {episode.answer or 'none recorded'}")
    return ok


def _format_delta(previous: StepStats | None, row_count: int | None) -> str:
    if previous is None or previous.row_count is None or row_count is None:
        return ""
    delta = row_count - previous.row_count
    if delta == 0:
        return " (unchanged)"
    return f" ({'+' if delta > 0 else ''}{delta} vs previous run)"
