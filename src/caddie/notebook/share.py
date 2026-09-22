"""`caddie notebook-share` - generate `notebook.portable.py`, a copy of
a project's notebook with no dependency on caddie itself, for handing
to someone who doesn't have (or want) caddie installed. See
`notebook/portable.py` for what "portable" means and its limits.
"""

import argparse
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.notebooks import find_project_dir, resolve_notebooks_root
from caddie.notebook.portable import render_portable_notebook


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-share",
        help="Generate a standalone copy of a project's notebook with no caddie dependency.",
    )
    parser.add_argument("--project", required=True, help="Existing project slug.")
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
    project_dir = find_project_dir(notebooks_root, args.project)
    if project_dir is None:
        raise SystemExit(f"No project '{args.project}' under {notebooks_root}.")

    try:
        out_path = render_portable_notebook(project_dir)
    except Exception as exc:
        raise SystemExit(str(exc))

    print(f"portable notebook: {out_path}")
    return 0
