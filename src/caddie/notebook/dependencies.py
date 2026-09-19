"""Computes the PEP 723 inline dependency header every generated
notebook starts with, so `marimo edit --sandbox` (see `notebook/edit.py`)
can build an isolated `uv` environment for it instead of running
against caddie's own shared venv.

The baseline mirrors caddie's own `pyproject.toml` dependencies, plus
caddie itself as a local `file://` dependency: every notebook's `setup`
cell imports `caddie.config.loader`/`caddie.connectors.loader` directly
(see `builder.py`), so caddie has to be importable inside a sandboxed
environment for that cell to run at all. A user who needs an extra
package for their own analysis code adds it with `caddie
notebook-add-dependency` (a thin wrapper over `uv add --script`), which
only touches that one notebook's own header - never caddie's shared
venv or pyproject.toml.

caddie is declared as a plain `file://` URL dependency rather than an
editable `[tool.uv.sources]` path: `marimo edit --sandbox` resolves a
script's dependencies via `uv export --no-header --script`, which (as
of uv 0.11.5) mis-serializes a local editable requirement as a bare
`-e` line with no path, breaking the sandbox. A `file://` URL exports
cleanly. The tradeoff is that a sandbox picks up caddie's source as of
whenever it was last resolved, not live - re-run `caddie
notebook-add-dependency` (or `uv add --script`/`uv lock --script`
directly) after changing caddie's own code to force a rebuild.
"""

import tomllib
from pathlib import Path

from marimo._utils.scripts import write_pyproject_to_script


def caddie_root() -> Path:
    """The checkout `caddie` itself is running from, resolved from the
    installed package rather than hardcoded - caddie is meant to be
    forked and cloned anywhere, so its own path isn't knowable in
    advance."""
    import caddie

    return Path(caddie.__file__).resolve().parents[2]


def _caddie_project_metadata() -> dict:
    pyproject_path = caddie_root() / "pyproject.toml"
    return tomllib.loads(pyproject_path.read_text())["project"]


def base_dependencies() -> list[str]:
    """caddie's own runtime dependencies, plus caddie itself (as a
    `file://` URL pointing at this checkout) - the minimum a sandboxed
    notebook needs to run its `setup` cell."""
    caddie_dep = f"caddie @ {caddie_root().as_uri()}"
    return [caddie_dep, *_caddie_project_metadata()["dependencies"]]


def render_script_header() -> str:
    """A PEP 723 `# /// script` block declaring `base_dependencies()`."""
    metadata = _caddie_project_metadata()
    project = {
        "requires-python": metadata["requires-python"],
        "dependencies": base_dependencies(),
    }
    return write_pyproject_to_script(project)


def render_portable_script_header() -> str:
    """The dependency header for a portable notebook (see
    `notebook/portable.py`): caddie's own runtime dependencies, minus
    caddie itself (the whole point of a portable notebook) and minus
    `ruamel-yaml` (only needed to read `caddie.yaml`, which a portable
    notebook's inlined setup cell never does)."""
    metadata = _caddie_project_metadata()
    deps = [dep for dep in metadata["dependencies"] if not dep.startswith("ruamel-yaml")]
    project = {"requires-python": metadata["requires-python"], "dependencies": deps}
    return write_pyproject_to_script(project)
