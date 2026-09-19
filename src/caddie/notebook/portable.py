"""Builds `notebook.portable.py`: a standalone copy of a project's
notebook with no dependency on the `caddie` package.

The working notebook's `setup` cell (see `builder.py`) delegates
connecting to data and applying Caddie's shared chart styling to
`caddie.config.loader`/`caddie.connectors.loader`/`caddie.charting`.
That's the right default while a project is actively worked on - it
always gets the latest, shared connector and template code - but it
means the notebook only runs where `caddie` is installed and
resolvable, which is a real limit on handing it to someone else.

`render_portable_notebook` produces a second file for that case: the
same cells, but with the `setup` cell's caddie imports replaced by the
literal source of the connector plugin actually used - vendored from
its own module, since every built-in connector is caddie-import-free
by design and so runs standalone - plus the charting template's
source, with the connector instantiated directly from the project's
saved settings instead of re-reading `caddie.yaml`. The vendored cell
is marked `hide_code` so it stays out of the way when opened.

This is a snapshot, not a live link: regenerate it (call this again)
after the connector or template code changes, or after the project's
connector settings change - it won't pick either up on its own. It
also only removes the dependency on the `caddie` package; whoever
opens the portable notebook still needs their own working access to
the same data backend (e.g. their own Databricks CLI profile).
"""

import inspect
from pathlib import Path
from types import ModuleType

from marimo._ast.cell import CellConfig
from marimo._ast.codegen import generate_filecontents

from caddie.charting import template as _template_module
from caddie.connectors.loader import resolve_connector_class
from caddie.notebook.builder import SETUP_CELL_NAME, notebook_path, read_cells
from caddie.notebook.dependencies import render_portable_script_header
from caddie.notebook.state import load_state

PORTABLE_FILENAME = "notebook.portable.py"


class NoProjectStateError(Exception):
    def __init__(self, project_dir: Path) -> None:
        super().__init__(
            f"No project state at {project_dir}; run notebook-start before notebook-share."
        )
        self.project_dir = project_dir


class NoNotebookError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(f"No notebook at {path}; run notebook-start first.")
        self.path = path


def portable_path(project_dir: Path) -> Path:
    return project_dir / PORTABLE_FILENAME


def _vendor_source(defined_in: type | ModuleType) -> str:
    """The literal source of the module `defined_in` lives in (a class
    pulls in its whole defining module, not just the class body, so
    module-level helpers it depends on come along too)."""
    return Path(inspect.getsourcefile(defined_in)).read_text().rstrip()


def _indent(source: str, spaces: int = 4) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in source.splitlines())


def _render_setup_cell(connector_name: str, connector_settings: dict) -> str:
    """Marimo requires each global name to have exactly one defining
    cell - unlike the original setup cell's `import ... as
    _caddie_template`, which only ever exposed the module object
    itself, splicing a vendored module's source in directly would leak
    every name it imports/defines (e.g. `go` for `plotly.graph_objects`)
    into the setup cell's globals, colliding with any chart cell that
    imports the same thing under the same alias (a `MultipleDefinitionError`
    that only surfaces once the notebook actually runs). Wrapping each
    vendored module in its own function and calling it restores that
    encapsulation - only the connector instance and the template's
    registration side effect are meant to be visible outside it."""
    connector_cls = resolve_connector_class(connector_name)
    connector_source = _vendor_source(connector_cls)
    template_source = _vendor_source(_template_module)

    kwargs = ", ".join(f"{key}={value!r}" for key, value in connector_settings.items())
    build_connector = (
        "def _caddie_build_connector():\n"
        f"{_indent(connector_source)}\n"
        f"    return {connector_cls.__name__}({kwargs})"
    )
    register_template = f"def _caddie_register_template():\n{_indent(template_source)}"

    return (
        "import marimo as mo\n\n"
        f"{build_connector}\n\n"
        f"{register_template}\n\n"
        "_caddie_register_template()\n"
        "conn = _caddie_build_connector()\n"
        "connector = conn"
    )


def render_portable_notebook(project_dir: Path) -> Path:
    state = load_state(project_dir)
    if state is None:
        raise NoProjectStateError(project_dir)

    src_path = notebook_path(project_dir)
    codes, names, configs = read_cells(src_path)
    if not names:
        raise NoNotebookError(src_path)

    setup_index = names.index(SETUP_CELL_NAME)
    codes[setup_index] = _render_setup_cell(state.connector, state.connector_settings)
    configs[setup_index] = CellConfig(hide_code=True)

    out_path = portable_path(project_dir)
    out_path.write_text(
        generate_filecontents(
            codes,
            names,
            configs,
            header_comments=render_portable_script_header(state.connector),
        )
    )
    return out_path
