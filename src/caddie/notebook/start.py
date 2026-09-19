"""`caddie notebook-start` - begin a new `/caddie-ask` episode: resolve
or create the project and write its question cell. No execution here -
a plan (`caddie notebook-plan`) is required before any step can run.
"""

import argparse
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.identity import resolve_username
from caddie.install.notebooks import ensure_user_notebooks_dir, resolve_notebooks_root
from caddie.notebook.builder import start_episode
from caddie.notebook.slug import slugify, unique_slug
from caddie.notebook.state import ProjectState, load_state, save_state


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-start",
        help="Start a new /caddie-ask episode (question cell only, no execution).",
    )
    parser.add_argument("--question", required=True, help="The literal question asked.")
    parser.add_argument(
        "--project",
        help="Existing project slug to add a new episode to. Omit to start a new project.",
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
    user_dir = ensure_user_notebooks_dir(notebooks_root, username)

    project_slug, project_dir = _resolve_project(args.project, args.question, user_dir)
    is_new_project = not project_dir.is_dir()

    question_markdown = f"**Question:** {args.question}"
    path, episode = start_episode(project_dir, question_markdown, config.connector)

    if is_new_project or load_state(project_dir) is None:
        save_state(
            project_dir,
            ProjectState(connector=config.connector, connector_settings=config.connector_settings),
        )

    print(f"project: {project_slug}")
    print(f"notebook: {path}")
    print(f"episode: {episode}")
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
