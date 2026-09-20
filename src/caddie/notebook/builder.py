"""Creates the one file operation an episode needs before any kernel
exists: the notebook itself, with its opening `question_{E}` cell.

One `/caddie-ask` question is an "episode": a `question_{E}` markdown
cell restating the ask, a `plan_{E}` markdown cell stating the
approach, an ordered sequence of `description_{E}_{S}` markdown +
`code_{E}_{S}`/`chart_{E}_{S}` + `output_{E}_{S}` steps sharing one
counter, and a final `answer_{E}` markdown cell. Episodes accumulate in
one project's notebook across a conversation's follow-ups, never
overwritten - only a plan cell is ever edited after the fact.

Every one of those cells past `question_{E}` is written by pairing with
the notebook's live marimo kernel (via the `marimo-pair` skill), not by
Caddie-core Python - see `.claude/skills/caddie-ask/SKILL.md` and
`.claude/agents/data-analyst.md` for the cell shapes and the pairing
sequence, and `.specs/requirements-marimo-pair.md` for why. Only
`question_{E}` has to happen here, before any kernel exists to attach
to: this module creates the notebook a kernel would attach to in the
first place.
"""

from pathlib import Path

from marimo._ast.cell import CellConfig
from marimo._ast.codegen import generate_filecontents, get_header_comments
from marimo._ast.load import get_notebook_status

from caddie.notebook.dependencies import render_script_header

NOTEBOOK_FILENAME = "notebook.py"

SETUP_CELL_NAME = "setup"
_SETUP_CODE = (
    "import marimo as mo\n"
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


def read_cells(path: Path) -> tuple[list[str], list[str], list[CellConfig]]:
    """Public entry point to `_existing_cells`, for callers outside this
    module that need a notebook's raw cell structure - e.g.
    `notebook/portable.py`, which rewrites the `setup` cell without
    reimplementing notebook parsing."""
    return _existing_cells(path)


def _write(
    path: Path,
    codes: list[str],
    names: list[str],
    configs: list[CellConfig],
    header: str | None = None,
) -> None:
    path.write_text(generate_filecontents(codes, names, configs, header_comments=header))


def start_episode(project_dir: Path, question_markdown: str, connector: str) -> tuple[Path, int]:
    """Create a brand-new project's notebook: its `setup` cell (with a
    PEP 723 header scoped to `connector`) and its first `question_1`
    cell. Returns (path, 1).

    This only ever runs once per project, for episode 1 - a project
    that already has a notebook already has a kernel a follow-up
    question can pair with, so every later episode's `question_{E}`
    (and everything else in every episode) is written by pairing with
    that kernel instead (see `.claude/skills/caddie-ask/SKILL.md`)."""
    project_dir.mkdir(parents=True, exist_ok=True)
    path = notebook_path(project_dir)
    if path.is_file():
        raise FileExistsError(
            f"{path} already exists - start_episode only creates a project's first episode."
        )

    header = render_script_header(connector)
    codes = [_SETUP_CODE, f"mo.md({question_markdown!r})"]
    names = [SETUP_CELL_NAME, "question_1"]
    configs = [CellConfig(), CellConfig()]

    _write(path, codes, names, configs, header)
    return path, 1


def refresh_header(project_dir: Path, connector: str) -> bool:
    """Rewrite an existing project's notebook to carry the PEP 723
    header `start_episode` would write today, leaving every cell
    untouched. Returns True if the file changed.

    A notebook's header is only ever written once, at `start_episode`
    - it never gets a second look after that, so a project created
    before `dependencies.py`'s `caddie @ file://...` fix (or before
    per-notebook headers existed at all) keeps whatever it was built
    with forever. That stale header is exactly what leaves `--sandbox`
    to resolve a bare `caddie==...` (or no `caddie` at all) against
    PyPI instead of this checkout - silently installing an unrelated,
    same-named package instead of failing loudly. `notebook-edit`
    calls this right before opening a session so the sandbox that
    session's kernel builds is never working from that stale header."""
    path = notebook_path(project_dir)
    new_header = render_script_header(connector)
    old_header = get_header_comments(str(path))
    if old_header is not None and old_header.strip() == new_header.strip():
        return False

    codes, names, configs = _existing_cells(path)
    _write(path, codes, names, configs, new_header)
    return True
