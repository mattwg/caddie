"""Exports a project's notebook to a standalone PDF, inputs and
outputs included - for handing an analysis to someone outside a
browser (email, Slack, an archive folder) rather than a click-to-open
HTML file or a live `marimo edit` session.

Its own CLI command, `caddie notebook-export`, is what `/caddie:export`
calls for a manual export, and what `caddie track-update` (the `Stop`
hook, see `caddie.cost.cli`) launches in the background after an
episode/explore turn ends, to keep the PDF in sync with the notebook
automatically.

Uses marimo's `--webpdf` exporter (nbconvert + a headless Chromium via
Playwright) rather than the default pandoc+TeX path - lighter to
install and renders embedded HTML/Plotly output faithfully. See
`caddie.install.tooling.ensure_chromium_installed`, wired into `caddie
install`/`caddie update`, for how Chromium gets onto a machine.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.notebooks import find_project_dir, resolve_notebooks_root
from caddie.notebook.builder import notebook_path


class ExportError(Exception):
    pass


def pdf_path(project_dir: Path) -> Path:
    # Named after the project rather than left as `notebook.pdf` -
    # every export would otherwise collide on that one filename once
    # shared outside its own folder (email, Slack, an archive). The
    # year/quarter prefix comes from the date partition
    # (`install.notebooks.partition_dir`) the project lives under:
    # `<root>/<year>/Q<quarter>/<month>/<date>/<slug>/`.
    year = project_dir.parents[3].name
    quarter = project_dir.parents[2].name
    slug = project_dir.name
    return project_dir / f"{year}-{quarter}-{slug}.pdf"


def export_notebook_pdf(project_dir: Path) -> Path:
    nb_path = notebook_path(project_dir)
    out_path = pdf_path(project_dir)

    # `-m marimo` on this same interpreter, same reasoning as
    # `notebook/render.py`'s `render_notebook`: the subprocess needs
    # the `caddie` package (and whatever else the notebook's setup
    # cell imports) available, which a bare `marimo` off PATH might not.
    #
    # `--sandbox` runs the export against the notebook's own PEP 723
    # header instead of caddie's shared venv (same mechanism
    # `notebook/edit.py`'s `start_server` already uses for `marimo
    # edit --sandbox`) - without it, a package added via `caddie
    # notebook-add-dependency` is missing here even though it's
    # available in a live edit session, so a cell that imports it
    # throws and the PDF can't even show the failing input code.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "marimo",
            "export",
            "pdf",
            str(nb_path),
            "--as=document",
            "--include-inputs",
            "--include-outputs",
            "--webpdf",
            "--sandbox",
            "-f",
            "-o",
            str(out_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ExportError(result.stderr.strip() or result.stdout.strip() or "marimo export pdf failed")
    return out_path


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-export",
        help="Export a project's notebook to a standalone PDF (inputs and outputs included).",
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

    print(f"project: {args.project}")

    try:
        exported = export_notebook_pdf(project_dir)
    except ExportError as exc:
        print("status: error")
        print(f"error: {exc}")
        return 1

    print(f"pdf: {exported}")
    print(f"open: file://{exported}")
    print("status: ok")
    return 0
