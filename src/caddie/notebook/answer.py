"""`caddie notebook-answer` - close out an episode with a real
natural-language conclusion, then render the whole notebook to a
static, fully-executed HTML file so the user has something to just
open - no further action needed.
"""

import argparse
import sys
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.identity import resolve_username
from caddie.install.notebooks import resolve_notebooks_root
from caddie.notebook.builder import (
    AlreadyAnsweredError,
    EpisodeNotFoundError,
    NoStepsYetError,
    append_answer,
    notebook_path,
)
from caddie.notebook.render import RenderError, render_notebook


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-answer",
        help="Write an episode's final answer and render the notebook.",
    )
    parser.add_argument("--project", required=True, help="Existing project slug.")
    parser.add_argument("--episode", required=True, type=int, help="Episode number within the project.")
    parser.add_argument(
        "--answer-file",
        help="File containing the answer markdown. Defaults to stdin.",
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
    answer_markdown = Path(args.answer_file).read_text() if args.answer_file else sys.stdin.read()

    print(f"project: {args.project}")

    try:
        append_answer(project_dir, args.episode, answer_markdown)
    except (EpisodeNotFoundError, NoStepsYetError, AlreadyAnsweredError) as exc:
        print("status: error")
        print(f"error: {exc}")
        return 1

    print(f"notebook: {notebook_path(project_dir)}")
    print(f"episode: {args.episode}")
    print("status: ok")

    try:
        rendered = render_notebook(project_dir)
        print(f"rendered: {rendered}")
        print(f"open: file://{rendered}")
    except RenderError as exc:
        print(f"render: error: {exc}")

    return 0
