"""Renders a project's notebook to a static, fully-executed HTML file.

A finished analysis shouldn't require the user to open `marimo edit`
and wait for it to re-run - completing an episode (or reloading a
project) hands back something they can just click open, already run,
already showing the real tables/charts/answer. This also doubles as an
independent, whole-file check: `marimo export html` runs every
episode/cell together via marimo's own reactive kernel, catching a
cross-cell issue a single step's own execution wouldn't see.

Exported with `--no-include-code`, so the click-to-open file reads
like marimo's App view (markdown, tables, charts) rather than Edit
view (raw code alongside everything else) - a stakeholder shouldn't
have to read SQL to see the answer.

Its own CLI command, `caddie notebook-render`, is what the `caddie-ask`
orchestrator calls once it's written an episode's `answer_{E}` cell by
pairing with the live kernel (see `.claude/skills/caddie-ask/SKILL.md`,
`.specs/requirements-marimo-pair.md`) - rendering is the only file
operation left once every cell write goes through the kernel instead.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.identity import resolve_username
from caddie.install.notebooks import resolve_notebooks_root
from caddie.notebook.builder import notebook_path


class RenderError(Exception):
    pass


def html_path(project_dir: Path) -> Path:
    return project_dir / "notebook.html"


def render_notebook(project_dir: Path) -> Path:
    nb_path = notebook_path(project_dir)
    out_path = html_path(project_dir)

    # `-m marimo` on this same interpreter, not a bare `marimo` off
    # PATH, so the subprocess has the `caddie` package (and whatever
    # else the notebook's setup cell imports) available - a bare
    # `marimo` could resolve to an unrelated install/environment.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "marimo",
            "export",
            "html",
            str(nb_path),
            "-o",
            str(out_path),
            "-f",
            "--no-include-code",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RenderError(result.stderr.strip() or result.stdout.strip() or "marimo export html failed")
    return out_path


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-render",
        help="Render a project's notebook to a static HTML file, without touching its cells.",
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

    username = config.username or resolve_username()
    notebooks_root = (
        Path(config.notebooks_root).expanduser()
        if config.notebooks_root
        else resolve_notebooks_root(None)
    )
    project_dir = notebooks_root / username / args.project

    print(f"project: {args.project}")

    try:
        rendered = render_notebook(project_dir)
    except RenderError as exc:
        print("status: error")
        print(f"error: {exc}")
        return 1

    print(f"rendered: {rendered}")
    print(f"open: file://{rendered}")
    print("status: ok")
    return 0
