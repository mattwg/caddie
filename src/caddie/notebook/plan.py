"""`caddie notebook-plan` - create or revise an episode's analysis
plan: the decision being supported, the scope (time range/segments/
granularity), and the anticipated approach - written before any query
runs, and updatable in place if execution reveals it was wrong.
"""

import argparse
import sys
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.identity import resolve_username
from caddie.install.notebooks import resolve_notebooks_root
from caddie.notebook.builder import EpisodeNotFoundError, notebook_path, upsert_plan


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-plan",
        help="Create or revise an episode's analysis plan.",
    )
    parser.add_argument("--project", required=True, help="Existing project slug.")
    parser.add_argument("--episode", required=True, type=int, help="Episode number within the project.")
    parser.add_argument(
        "--plan-file",
        help="File containing the plan markdown. Defaults to stdin.",
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

    plan_markdown = Path(args.plan_file).read_text() if args.plan_file else sys.stdin.read()

    print(f"project: {args.project}")

    try:
        upsert_plan(project_dir, args.episode, plan_markdown)
    except EpisodeNotFoundError as exc:
        print("status: error")
        print(f"error: {exc}")
        return 1

    print(f"notebook: {notebook_path(project_dir)}")
    print(f"episode: {args.episode}")
    print("status: ok")
    return 0
