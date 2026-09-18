"""Builds and appends Marimo notebooks from analytics-skill output.

Each question becomes a group of three cells appended to a single
project notebook: a markdown cell (the skill's markdown, which itself
restates the literal question), a code cell that runs the skill's
returned code through the connector's `execute()`, and a designated
output cell. Groups are appended, never rewritten, so a project's
notebook grows across a conversation instead of a new file being
created per question.

This is the notebook-lifecycle mechanics that requirements.md calls
"ordinary Caddie-core code" shared by `/caddie-ask` and `/caddie-load`
- not a script-backed command in the install/update/list sense, since
what to build/append is decided per call, not by a fixed set of steps.
No execution happens here (see Step 12); this only ever produces a
valid, unexecuted `.py` Marimo notebook.
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from marimo._ast.cell import CellConfig
from marimo._ast.codegen import generate_filecontents
from marimo._ast.load import get_notebook_status

NOTEBOOK_FILENAME = "notebook.py"

_SETUP_CELL_NAME = "setup"
_SETUP_CODE = (
    "from caddie.charting import template as _caddie_template\n"
    "from caddie.config.loader import load_config\n"
    "from caddie.connectors.loader import load_connector_from_config\n"
    "\n"
    "config = load_config()\n"
    "connector = load_connector_from_config(config)\n"
    "conn = connector"
)


class InvalidNotebookError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} exists but is not a valid Marimo notebook.")
        self.path = path


_QUERY_CELL_RE = re.compile(
    r"^query_\d+\s*=\s*(.+?)\nresult_\d+\s*=\s*conn\.execute\(query_\d+\)\s*$", re.DOTALL
)
_MARKDOWN_CELL_RE = re.compile(r"^mo\.md\((.+)\)$", re.DOTALL)


@dataclass(frozen=True)
class NotebookGroup:
    index: int
    markdown: str
    code: str


def notebook_path(project_dir: Path) -> Path:
    return project_dir / NOTEBOOK_FILENAME


def _existing_cells(path: Path) -> tuple[list[str], list[str], list[CellConfig]]:
    """Return (codes, names, configs) for every cell already in the
    notebook at `path`, or three empty lists if it doesn't exist yet."""
    if not path.is_file():
        return [], [], []

    result = get_notebook_status(str(path))
    if result.notebook is None:
        raise InvalidNotebookError(path)

    codes = [cell.code for cell in result.notebook.cells]
    names = [cell.name for cell in result.notebook.cells]
    configs = [CellConfig.from_dict(cell.options) for cell in result.notebook.cells]
    return codes, names, configs


def _next_group_index(names: list[str]) -> int:
    indices = [
        int(name.rsplit("_", 1)[1])
        for name in names
        if name.startswith("question_") and name.rsplit("_", 1)[1].isdigit()
    ]
    return max(indices, default=0) + 1


def build_or_append_notebook(project_dir: Path, markdown: str, code: str) -> tuple[Path, int]:
    """Create the project's notebook, or append a new cell group to it.

    `markdown` and `code` are the analytics skill's already-parsed
    output (see skills/parser.py) - the markdown cell gets `markdown`
    verbatim, and the code cell wraps `code` in a call through the
    connector session set up in the notebook's setup cell.

    Returns the absolute path to the notebook file and the 1-based
    index of the group just written.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    path = notebook_path(project_dir)

    codes, names, configs = _existing_cells(path)
    if not names:
        codes, names, configs = [_SETUP_CODE], [_SETUP_CELL_NAME], [CellConfig()]

    group = _next_group_index(names)
    question_cell = f"mo.md({markdown!r})"
    code_cell = f"query_{group} = {code!r}\nresult_{group} = conn.execute(query_{group})"
    output_cell = f"result_{group}"

    codes += [question_cell, code_cell, output_cell]
    names += [f"question_{group}", f"code_{group}", f"output_{group}"]
    configs += [CellConfig(), CellConfig(), CellConfig()]

    path.write_text(generate_filecontents(codes, names, configs))
    return path, group


def existing_groups(project_dir: Path) -> list[NotebookGroup]:
    """Read back every question/code cell group already in a project's
    notebook, in order — the original question markdown and code
    string, reconstructed from the cell source `build_or_append_notebook`
    generated. Used by `/caddie-load`-style re-execution, which needs
    the original code strings, not the notebook's own reactive cells.
    """
    path = notebook_path(project_dir)
    codes, names, _ = _existing_cells(path)

    markdown_by_index: dict[int, str] = {}
    code_by_index: dict[int, str] = {}
    for name, cell_code in zip(names, codes):
        if name.startswith("question_"):
            markdown_by_index[int(name.rsplit("_", 1)[1])] = _extract_markdown(cell_code)
        elif name.startswith("code_"):
            code_by_index[int(name.rsplit("_", 1)[1])] = _extract_query_code(cell_code)

    return [
        NotebookGroup(index=i, markdown=markdown_by_index[i], code=code_by_index[i])
        for i in sorted(code_by_index)
    ]


def _extract_markdown(cell_code: str) -> str:
    match = _MARKDOWN_CELL_RE.match(cell_code.strip())
    if not match:
        raise InvalidNotebookError(Path("<question cell>"))
    return ast.literal_eval(match.group(1))


def _extract_query_code(cell_code: str) -> str:
    match = _QUERY_CELL_RE.match(cell_code.strip())
    if not match:
        raise InvalidNotebookError(Path("<code cell>"))
    return ast.literal_eval(match.group(1))
