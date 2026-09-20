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

The header only includes the dependencies the project's actual
connector needs, not caddie's full dependency list - see
`_BUILTIN_CONNECTOR_ONLY_DEPS` below for why that isn't simply "read
caddie's pyproject.toml as-is."

`data-analyst` pairs with the sandboxed kernel this header builds via
the `marimo-pair` skill's own `execute-code.sh`, which talks to
marimo's HTTP API directly (see `notebook/edit.py`) - this needs no
extra dependency beyond `marimo` itself (code mode shipped in v0.21.1;
see the version floor in caddie's own `pyproject.toml`).

Caddie's own `marimo` dependency also carries the `[sandbox]` extra
(for `pyzmq`), but that's only needed by the *shared, directory-level*
`marimo edit` process `notebook-edit` runs against caddie's own venv
(see `notebook/edit.py`) - a single per-notebook header never needs it,
so `_without_sandbox_extra` strips it back off before it reaches a
notebook's own PEP 723 block.
"""

import tomllib
from pathlib import Path

from marimo._utils.scripts import write_pyproject_to_script

# Dependencies in caddie's own pyproject.toml that exist only to
# support one specific built-in connector, keyed by connector name -
# so a notebook using a different connector doesn't declare (and pay
# the install cost of) a package it will never import. `databricks`
# and `fake` are both registered inside caddie's own distribution (see
# pyproject.toml's `caddie.connectors` entry points), so there's no
# separate installed package to ask for accurate per-connector
# metadata the way a genuinely separate third-party connector plugin
# would have - this mapping is the pragmatic stand-in for that.
#
# Deliberately not fixed by splitting caddie's own pyproject.toml into
# per-connector `[project.optional-dependencies]` groups instead: every
# `caddie` invocation goes through `uv run` (see every SKILL.md), which
# re-syncs the venv to match the *base* dependency list before running
# - it does not preserve extras installed by a one-off `uv sync
# --extra databricks` call, so a real Databricks user's very next
# plain `caddie` command would silently lose the package again. Fixing
# that properly would mean threading a per-connector `--extra` flag
# through every skill's invocation, which is a bigger and riskier
# change than this dependency-scoping problem calls for.
_BUILTIN_CONNECTOR_ONLY_DEPS: dict[str, list[str]] = {
    "databricks": ["databricks-connect"],
}


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


def _dependency_name(requirement: str) -> str:
    for sep in ("@", ">=", "==", "<=", "~=", ">", "<", "[", ";"):
        requirement = requirement.split(sep, 1)[0]
    return requirement.strip()


def _without_sandbox_extra(dep: str) -> str:
    """Strip a `[sandbox]` extra off caddie's own `marimo` requirement
    before it reaches a per-notebook header - that extra (`pyzmq`) is
    only needed by the shared, directory-level `marimo edit` process
    `notebook-edit` runs, never by an individual notebook's own
    single-file sandbox."""
    if _dependency_name(dep) == "marimo" and "[sandbox]" in dep:
        return dep.replace("[sandbox]", "")
    return dep


def _connector_agnostic_dependencies() -> list[str]:
    """caddie's own dependencies, minus every entry that
    `_BUILTIN_CONNECTOR_ONLY_DEPS` attributes to a specific connector -
    the part every notebook needs regardless of which connector it
    uses."""
    connector_only = {
        name for names in _BUILTIN_CONNECTOR_ONLY_DEPS.values() for name in names
    }
    return [
        _without_sandbox_extra(dep)
        for dep in _caddie_project_metadata()["dependencies"]
        if _dependency_name(dep) not in connector_only
    ]


def _connector_dependencies(connector_name: str) -> list[str]:
    """The subset of caddie's own dependencies that `connector_name`
    actually needs, beyond the connector-agnostic base. A connector not
    listed in `_BUILTIN_CONNECTOR_ONLY_DEPS` (a genuinely separate,
    installed-elsewhere connector plugin) gets nothing extra here - its
    own package's install metadata already covers its needs
    independently of caddie."""
    wanted = set(_BUILTIN_CONNECTOR_ONLY_DEPS.get(connector_name, []))
    if not wanted:
        return []
    return [
        dep for dep in _caddie_project_metadata()["dependencies"] if _dependency_name(dep) in wanted
    ]


def base_dependencies(connector_name: str) -> list[str]:
    """caddie itself (as a `file://` URL pointing at this checkout),
    plus its connector-agnostic dependencies, plus whatever
    `connector_name` specifically needs - the minimum a sandboxed
    notebook using that connector needs to run its `setup` cell."""
    caddie_dep = f"caddie @ {caddie_root().as_uri()}"
    return [
        caddie_dep,
        *_connector_agnostic_dependencies(),
        *_connector_dependencies(connector_name),
    ]


def render_script_header(connector_name: str) -> str:
    """A PEP 723 `# /// script` block declaring `base_dependencies()`
    for the project's actual connector."""
    metadata = _caddie_project_metadata()
    project = {
        "requires-python": metadata["requires-python"],
        "dependencies": base_dependencies(connector_name),
    }
    return write_pyproject_to_script(project)


def render_portable_script_header(connector_name: str) -> str:
    """The dependency header for a portable notebook (see
    `notebook/portable.py`): the connector-agnostic dependencies (minus
    `ruamel-yaml`, only needed to read `caddie.yaml`, which a portable
    notebook's inlined setup cell never does) plus what the project's
    actual connector needs - never caddie itself, the whole point of a
    portable notebook."""
    deps = [
        dep for dep in _connector_agnostic_dependencies() if not dep.startswith("ruamel-yaml")
    ] + _connector_dependencies(connector_name)
    metadata = _caddie_project_metadata()
    project = {"requires-python": metadata["requires-python"], "dependencies": deps}
    return write_pyproject_to_script(project)
