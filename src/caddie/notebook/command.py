"""`caddie notebook-build` - build or append a Marimo notebook cell
group from an analytics skill's raw output, without executing it.

The `/caddie-ask` skill decides *when* to call this (new project vs.
an implicit or explicit continuation) and invokes the configured
analytics skill itself (via the Skill tool - that only happens inside
a live Claude Code session, not here); this command only turns the
question plus that skill's raw text output into notebook cells.
"""

import argparse
import sys
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.identity import resolve_username
from caddie.install.notebooks import ensure_user_notebooks_dir, resolve_notebooks_root
from caddie.notebook.builder import build_or_append_notebook
from caddie.notebook.slug import slugify, unique_slug
from caddie.skills.parser import parse_skill_output


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-build",
        help="Build or append a Marimo notebook cell group from a skill's output.",
    )
    parser.add_argument("--question", required=True, help="The literal question asked.")
    parser.add_argument(
        "--project",
        help="Existing project slug to append to. Omit to start a new project.",
    )
    parser.add_argument(
        "--skill-output-file",
        help="File containing the invoked skill's raw output. Defaults to stdin.",
    )
    parser.add_argument(
        "--config-path",
        help="Override the caddie.yaml path (mainly for testing).",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path) if args.config_path else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    raw_output = (
        Path(args.skill_output_file).read_text()
        if args.skill_output_file
        else sys.stdin.read()
    )
    skill_output = parse_skill_output(raw_output)

    username = config.username or resolve_username()
    notebooks_root = (
        Path(config.notebooks_root).expanduser()
        if config.notebooks_root
        else resolve_notebooks_root(None)
    )
    user_dir = ensure_user_notebooks_dir(notebooks_root, username)

    project_slug, project_dir = _resolve_project(args.project, args.question, user_dir)

    path = build_or_append_notebook(project_dir, skill_output.markdown, skill_output.code)

    print(f"project: {project_slug}")
    print(f"notebook: {path}")
    return 0


def _resolve_project(
    explicit_project: str | None, question: str, user_dir: Path
) -> tuple[str, Path]:
    if explicit_project:
        project_dir = user_dir / explicit_project
        if not project_dir.is_dir():
            raise SystemExit(
                f"No existing project '{explicit_project}' under {user_dir}; "
                "omit --project to start a new one."
            )
        return explicit_project, project_dir

    existing = {p.name for p in user_dir.iterdir() if p.is_dir()} if user_dir.is_dir() else set()
    project_slug = unique_slug(slugify(question), existing)
    return project_slug, user_dir / project_slug
