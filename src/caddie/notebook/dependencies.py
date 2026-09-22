"""Computes the PEP 723 inline dependency header every generated
notebook starts with, so `marimo edit --sandbox` (see `notebook/edit.py`)
can build an isolated `uv` environment for it instead of running
against caddie's own shared venv.

The baseline mirrors caddie's own declared dependencies, plus caddie
itself pinned to its own installed version (`caddie==<version>`):
every notebook's `setup` cell imports `caddie.config.loader`/
`caddie.connectors.loader` directly (see `builder.py`), so caddie has
to be importable inside a sandboxed environment for that cell to run
at all. A user who needs an extra package for their own analysis code
adds it with `caddie notebook-add-dependency` (a thin wrapper over `uv
add --script`), which only touches that one notebook's own header -
never caddie's shared venv or install.

caddie is declared as a version-pinned requirement (`caddie==<version>`)
rather than a local path or `file://` URL: once caddie is installed as
a regular tool (`uv tool install ...`) rather than an editable git
checkout, there's no local project path to point a dependency at. The
tradeoff is that a sandbox picks up whatever version of caddie was
installed at header-generation time, not necessarily the very latest -
re-run `caddie update` (or `caddie notebook-edit`, which refreshes the
header - see `notebook/edit.py`) after upgrading caddie to pick up a
new pin.

Caddie isn't published on PyPI - it's installed via `uv tool install
git+https://github.com/mattwg/caddie` (or another git remote/fork).
A bare `caddie==<version>` requirement in the header would ask `uv`'s
sandbox resolver to fetch that name from PyPI instead, which can
silently resolve to a same-named, unrelated PyPI project instead of
failing loudly. So whenever caddie's own installed distribution was
itself sourced from git (detected via `direct_url.json` - see
`_caddie_git_source` below), the header also carries a
`[tool.uv.sources]` entry pinning `caddie` back to that same git URL,
overriding the bare version requirement for anyone whose `uv tool
install` command matches how this notebook's own header was built. A
caddie installed straight from a real PyPI release (no `direct_url.json`,
or one without `vcs_info`) needs no such override - the plain version
pin already resolves correctly.

The header only includes the dependencies the project's actual
connector needs, not caddie's full dependency list - see
`_BUILTIN_CONNECTOR_ONLY_DEPS` below for why that isn't simply "read
caddie's own installed metadata as-is."

Caddie's own declared dependencies and version are read via
`importlib.metadata` rather than parsing `pyproject.toml` off disk -
that file only exists next to an editable git checkout, not next to an
installed wheel (see requirements-plugin.md, "Caddie's own root is no
longer knowable"). `importlib.metadata` reads a package's own
installed distribution metadata, which is present either way.

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

import importlib.metadata
import json

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


def _caddie_version() -> str:
    return importlib.metadata.version("caddie")


def _caddie_requires_python() -> str:
    return importlib.metadata.metadata("caddie")["Requires-Python"]


def _caddie_dependencies() -> list[str]:
    return list(importlib.metadata.requires("caddie") or [])


def _caddie_git_source() -> str | None:
    """The git URL caddie's own installed distribution was resolved
    from, or `None` if it was installed from a real PyPI release (or
    some other non-VCS source).

    `direct_url.json` is written into a distribution's `dist-info` by
    pip/uv whenever the requirement they installed was a VCS or direct
    URL rather than a plain PyPI name - see
    https://packaging.python.org/en/latest/specifications/direct-url/.
    It's absent for an ordinary PyPI install, which is exactly the
    signal used here."""
    raw = importlib.metadata.distribution("caddie").read_text("direct_url.json")
    if not raw:
        return None
    info = json.loads(raw)
    vcs_info = info.get("vcs_info")
    if not vcs_info or vcs_info.get("vcs") != "git":
        return None
    return info.get("url")


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
        for dep in _caddie_dependencies()
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
        dep for dep in _caddie_dependencies() if _dependency_name(dep) in wanted
    ]


def base_dependencies(connector_name: str) -> list[str]:
    """caddie itself (pinned to its own installed version), plus its
    connector-agnostic dependencies, plus whatever `connector_name`
    specifically needs - the minimum a sandboxed notebook using that
    connector needs to run its `setup` cell."""
    caddie_dep = f"caddie=={_caddie_version()}"
    return [
        caddie_dep,
        *_connector_agnostic_dependencies(),
        *_connector_dependencies(connector_name),
    ]


def render_script_header(connector_name: str) -> str:
    """A PEP 723 `# /// script` block declaring `base_dependencies()`
    for the project's actual connector - plus a `[tool.uv.sources]`
    pin for `caddie` itself back to its own git remote, if that's
    where this install of caddie came from (see `_caddie_git_source`),
    so the sandbox resolver doesn't fall through to an unrelated,
    same-named PyPI project."""
    project = {
        "requires-python": _caddie_requires_python(),
        "dependencies": base_dependencies(connector_name),
    }
    git_source = _caddie_git_source()
    if git_source:
        project["tool"] = {"uv": {"sources": {"caddie": {"git": git_source}}}}
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
    project = {"requires-python": _caddie_requires_python(), "dependencies": deps}
    return write_pyproject_to_script(project)
