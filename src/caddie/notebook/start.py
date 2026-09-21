"""`caddie notebook-start` - create a brand-new project: its notebook
file and first `question_1` cell. This is the one write that has to
happen before any kernel exists to attach to - a follow-up question in
an already-existing project pairs with that project's kernel instead
and writes its `question_{E}` cell through it (see
`.claude/skills/caddie-ask/SKILL.md`), never through this command.
"""

import argparse
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.notebooks import ensure_notebooks_dir, resolve_notebooks_root
from caddie.notebook.builder import start_episode
from caddie.notebook.slug import slugify, unique_slug
from caddie.notebook.state import ProjectState, save_state


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-start",
        help="Create a new project and its first episode (question cell only, no execution).",
    )
    parser.add_argument("--question", required=True, help="The literal question asked.")
    parser.add_argument(
        "--config-path",
        help="Override the caddie.yaml path (mainly for testing).",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path) if args.config_path else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    notebooks_root = (
        Path(config.notebooks_root).expanduser()
        if config.notebooks_root
        else resolve_notebooks_root(None)
    )
    notebooks_dir = ensure_notebooks_dir(notebooks_root)

    existing = (
        {p.name for p in notebooks_dir.iterdir() if p.is_dir()} if notebooks_dir.is_dir() else set()
    )
    project_slug = unique_slug(slugify(args.question), existing)
    project_dir = notebooks_dir / project_slug

    question_markdown = f"**Question:** {args.question}"
    path, episode = start_episode(project_dir, question_markdown, config.connector)

    save_state(
        project_dir,
        ProjectState(connector=config.connector, connector_settings=config.connector_settings),
    )

    print(f"project: {project_slug}")
    print(f"notebook: {path}")
    print(f"episode: {episode}")
    return 0
