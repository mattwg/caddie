"""Renders a project's notebook to a static, fully-executed HTML file.

A finished analysis shouldn't require the user to open `marimo edit`
and wait for it to re-run - completing an episode (or reloading a
project) hands back something they can just click open, already run,
already showing the real tables/charts/answer. This also doubles as an
independent, whole-file check: `marimo export html` runs every
episode/cell together via marimo's own reactive kernel, catching a
cross-cell issue the per-step checks in executor.py wouldn't see.
"""

import subprocess
import sys
from pathlib import Path

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
        [sys.executable, "-m", "marimo", "export", "html", str(nb_path), "-o", str(out_path), "-f"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RenderError(result.stderr.strip() or result.stdout.strip() or "marimo export html failed")
    return out_path
