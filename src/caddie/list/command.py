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
from caddie.install.notebooks import resolve_notebooks_root

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

    notebooks_root = (
        Path(config.notebooks_root).expanduser()
        if config.notebooks_root
        else resolve_notebooks_root(None)
    )

    projects = _discover(notebooks_root, args.pattern)
    if args.recent is not None:
        projects = projects[: args.recent]

    if not projects:
        print("no projects found")
        return 0

    for slug, mtime in projects:
        print(f"{slug}\t{_format_mtime(mtime)}")
    return 0


def _discover(notebooks_root: Path, pattern: str | None) -> list[tuple[str, float]]:
    if not notebooks_root.is_dir():
        return []

    # Projects live under a year/quarter/month/date partition
    # (`install/notebooks.py:partition_dir`), so this has to walk the
    # whole tree rather than list the root's immediate children.
    projects = []
    for nb_path in notebooks_root.rglob("notebook.py"):
        slug = nb_path.parent.name
        if pattern and not fnmatch.fnmatch(slug, pattern):
            continue
        projects.append((slug, nb_path.stat().st_mtime))

    projects.sort(key=lambda p: p[1], reverse=True)
    return projects


def _format_mtime(mtime: float) -> str:
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
