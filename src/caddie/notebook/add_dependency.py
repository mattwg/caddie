"""`caddie notebook-add-dependency` - add a package to one project's
notebook, without touching caddie's own shared venv or pyproject.toml.

A thin wrapper over `uv add --script`, which edits the notebook's own
PEP 723 header in place (see `notebook/dependencies.py` for how that
header is first written). The added package only takes effect the next
time that notebook is opened with `caddie notebook-edit --sandbox`
(the default) - it has no effect on `/caddie-ask`'s own step execution,
which runs in-process against caddie's shared venv so it can share a
live connector session, and so is limited to whatever's already
installed there.
"""

import argparse
import shutil
import subprocess
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.notebooks import resolve_notebooks_root
from caddie.notebook.builder import notebook_path


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-add-dependency",
        help="Add a package to a project's notebook (its own sandboxed env, not caddie's).",
    )
    parser.add_argument("--project", required=True, help="Existing project slug.")
    parser.add_argument(
        "package", help="Package requirement to add, e.g. 'scikit-learn' or 'pandas>=2'."
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
    project_dir = notebooks_root / args.project
    nb_path = notebook_path(project_dir)
    if not nb_path.is_file():
        raise SystemExit(f"No project '{args.project}' under {notebooks_root}.")

    uv_bin = shutil.which("uv")
    if uv_bin is None:
        raise SystemExit("uv is required to add a notebook dependency (not found on PATH).")

    result = subprocess.run(
        [uv_bin, "add", "--script", str(nb_path), args.package],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or f"uv add failed for {args.package!r}.")

    print(f"added: {args.package}")
    print(f"notebook: {nb_path}")
    return 0
