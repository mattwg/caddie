"""`caddie list` — read-only discovery of the user's existing analysis
projects: glob the notebooks folder, most-recently-modified first.

Purely a filesystem query against the notebooks root recorded in
`caddie.yaml` — never creates, modifies, deletes, or executes a
notebook. The `/caddie-list` skill invokes this and relays its output
rather than walking the filesystem itself.
"""

import argparse
import fnmatch
from datetime import datetime
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.identity import resolve_username
from caddie.install.notebooks import resolve_notebooks_root
from caddie.notebook.builder import notebook_path

DEFAULT_RECENT = 10


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "list", help="List existing analysis projects, most recently modified first."
    )
    parser.add_argument(
        "pattern", nargs="?", help="ls-style wildcard matched against project slugs."
    )
    parser.add_argument(
        "--recent",
        nargs="?",
        type=int,
        const=DEFAULT_RECENT,
        default=None,
        help=f"Limit to the N most recently modified projects (default {DEFAULT_RECENT} "
        "if given with no value).",
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
    user_dir = notebooks_root / username

    projects = _discover(user_dir, args.pattern)
    if args.recent is not None:
        projects = projects[: args.recent]

    if not projects:
        print("no projects found")
        return 0

    for slug, mtime in projects:
        print(f"{slug}\t{_format_mtime(mtime)}")
    return 0


def _discover(user_dir: Path, pattern: str | None) -> list[tuple[str, float]]:
    if not user_dir.is_dir():
        return []

    projects = []
    for entry in user_dir.iterdir():
        if not entry.is_dir():
            continue
        nb_path = notebook_path(entry)
        if not nb_path.is_file():
            continue
        if pattern and not fnmatch.fnmatch(entry.name, pattern):
            continue
        projects.append((entry.name, nb_path.stat().st_mtime))

    projects.sort(key=lambda p: p[1], reverse=True)
    return projects


def _format_mtime(mtime: float) -> str:
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
