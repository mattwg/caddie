"""Builds and edits Marimo notebooks from `/caddie-ask` episodes.

One `/caddie-ask` question is an "episode": a `question_{E}` markdown
cell restating the ask, a `plan_{E}` markdown cell stating the
approach (revisable in place if execution reveals it was wrong), an
ordered sequence of `code_{E}_{S}`/`chart_{E}_{S}` + `output_{E}_{S}`
steps sharing one counter, and a final `answer_{E}` markdown cell.
Episodes accumulate in one project's notebook across a conversation's
follow-ups, never overwritten - only a plan cell is ever edited after
the fact, and only in place.

This is the notebook-lifecycle mechanics that requirements.md calls
"ordinary Caddie-core code" shared by `/caddie-ask` and `/caddie-load`
- not a script-backed command in the install/update/list sense, since
what to build/append/revise is decided per call, not a fixed sequence.
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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


class EpisodeNotFoundError(Exception):
    def __init__(self, episode: int, path: Path) -> None:
        super().__init__(f"No episode {episode} in {path}.")
        self.episode = episode


class PlanRequiredError(Exception):
    def __init__(self, episode: int) -> None:
        super().__init__(
            f"Episode {episode} has no plan yet; call notebook-plan before notebook-step."
        )
        self.episode = episode


class NoStepsYetError(Exception):
    def __init__(self, episode: int) -> None:
        super().__init__(f"Episode {episode} has no steps yet; nothing to answer.")
        self.episode = episode


class AlreadyAnsweredError(Exception):
    def __init__(self, episode: int) -> None:
        super().__init__(f"Episode {episode} already has an answer.")
        self.episode = episode


_QUERY_CELL_RE = re.compile(
    r"^(?:#[^\n]*\n)?query_\d+_\d+\s*=\s*(.+?)\nresult_\d+_\d+\s*=\s*conn\.execute\(query_\d+_\d+\)\s*$",
    re.DOTALL,
)
_MARKDOWN_CELL_RE = re.compile(r"^mo\.md\((.+)\)$", re.DOTALL)
_QUESTION_NAME_RE = re.compile(r"^question_(\d+)$")
_PLAN_NAME_RE = re.compile(r"^plan_(\d+)$")
_STEP_NAME_RE = re.compile(r"^(code|chart)_(\d+)_(\d+)$")
_ANSWER_NAME_RE = re.compile(r"^answer_(\d+)$")


@dataclass(frozen=True)
class NotebookStep:
    episode: int
    step: int
    kind: Literal["query", "chart"]
    code: str


@dataclass(frozen=True)
class NotebookEpisode:
    index: int
    question: str
    plan: str | None
    steps: list[NotebookStep]
    answer: str | None


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


def _next_episode_index(names: list[str]) -> int:
    indices = [int(m.group(1)) for name in names if (m := _QUESTION_NAME_RE.match(name))]
    return max(indices, default=0) + 1


def _next_step_index(names: list[str], episode: int) -> int:
    pattern = re.compile(rf"^(?:code|chart)_{episode}_(\d+)$")
    indices = [int(m.group(1)) for name in names if (m := pattern.match(name))]
    return max(indices, default=0) + 1


def start_episode(project_dir: Path, question_markdown: str, connector: str) -> tuple[Path, int]:
    """Create the project's notebook if needed and start a new episode:
    writes only its `question_{E}` cell. No plan, no steps yet - those
    come from `upsert_plan`/`append_step`. Returns (path, episode).

    `connector` only matters for a brand-new notebook, to scope its
    dependency header to what that connector actually needs (see
    `notebook/dependencies.py`); an existing notebook keeps whatever
    header it already has."""
    project_dir.mkdir(parents=True, exist_ok=True)
    path = notebook_path(project_dir)

    codes, names, configs = _existing_cells(path)
    if not names:
        codes, names, configs = [_SETUP_CODE], [SETUP_CELL_NAME], [CellConfig()]
        header = render_script_header(connector)
    else:
        header = get_header_comments(path)

    episode = _next_episode_index(names)
    codes.append(f"mo.md({question_markdown!r})")
    names.append(f"question_{episode}")
    configs.append(CellConfig())

    _write(path, codes, names, configs, header)
    return path, episode


def upsert_plan(project_dir: Path, episode: int, plan_markdown: str) -> None:
    """Create an episode's plan cell, or overwrite it in place if one
    already exists - this is how a plan gets revised mid-episode
    without losing its position (right after the question cell)."""
    path = notebook_path(project_dir)
    codes, names, configs = _existing_cells(path)
    header = get_header_comments(path)

    if f"question_{episode}" not in names:
        raise EpisodeNotFoundError(episode, path)

    plan_name = f"plan_{episode}"
    plan_code = f"mo.md({plan_markdown!r})"
    if plan_name in names:
        codes[names.index(plan_name)] = plan_code
    else:
        insert_at = names.index(f"question_{episode}") + 1
        codes.insert(insert_at, plan_code)
        names.insert(insert_at, plan_name)
        configs.insert(insert_at, CellConfig())

    _write(path, codes, names, configs, header)


def append_step(
    project_dir: Path,
    episode: int,
    code: str,
    kind: Literal["query", "chart"] = "query",
    label: str | None = None,
) -> int:
    """Append the next step (query or chart) plus its output cell to an
    already-planned episode. Returns the new step number.

    A query step's cell wraps `code` through the connector, same as
    before. A chart step's cell is `code` verbatim - Claude-authored
    Python expected to assign a Plotly figure to `chart_{E}_{S}`,
    referencing an earlier step's `result_{E}_{S}`.
    """
    path = notebook_path(project_dir)
    codes, names, configs = _existing_cells(path)
    header = get_header_comments(path)

    if f"question_{episode}" not in names:
        raise EpisodeNotFoundError(episode, path)
    if f"plan_{episode}" not in names:
        raise PlanRequiredError(episode)

    step = _next_step_index(names, episode)
    var_prefix = f"{episode}_{step}"

    if kind == "query":
        cell_name = f"code_{var_prefix}"
        body = f"query_{var_prefix} = {code!r}\nresult_{var_prefix} = conn.execute(query_{var_prefix})"
        output_body = f"result_{var_prefix}"
    else:
        cell_name = f"chart_{var_prefix}"
        body = code
        output_body = f"chart_{var_prefix}"

    if label:
        body = f"# {label}\n{body}"

    codes += [body, output_body]
    names += [cell_name, f"output_{var_prefix}"]
    configs += [CellConfig(), CellConfig()]

    _write(path, codes, names, configs, header)
    return step


def append_answer(project_dir: Path, episode: int, answer_markdown: str) -> None:
    """Append an episode's final answer cell. Raises if the episode has
    no steps yet, or already has an answer - one answer per episode."""
    path = notebook_path(project_dir)
    codes, names, configs = _existing_cells(path)
    header = get_header_comments(path)

    if f"question_{episode}" not in names:
        raise EpisodeNotFoundError(episode, path)

    step_pattern = re.compile(rf"^(?:code|chart)_{episode}_\d+$")
    if not any(step_pattern.match(name) for name in names):
        raise NoStepsYetError(episode)
    if f"answer_{episode}" in names:
        raise AlreadyAnsweredError(episode)

    codes.append(f"mo.md({answer_markdown!r})")
    names.append(f"answer_{episode}")
    configs.append(CellConfig())

    _write(path, codes, names, configs, header)


def existing_episodes(project_dir: Path) -> list[NotebookEpisode]:
    """Reconstruct every episode already in a project's notebook, in
    order: its question, current plan (if any), ordered steps (with
    their original code, not the wrapped cell body), and answer (if
    any). Used by `/caddie-load`-style re-execution and by chart steps
    that need to replay an episode's earlier queries."""
    path = notebook_path(project_dir)
    codes, names, _ = _existing_cells(path)

    questions: dict[int, str] = {}
    plans: dict[int, str] = {}
    steps: dict[int, list[NotebookStep]] = {}
    answers: dict[int, str] = {}

    for name, cell_code in zip(names, codes):
        if m := _QUESTION_NAME_RE.match(name):
            questions[int(m.group(1))] = _extract_markdown(cell_code)
        elif m := _PLAN_NAME_RE.match(name):
            plans[int(m.group(1))] = _extract_markdown(cell_code)
        elif m := _STEP_NAME_RE.match(name):
            raw_kind, episode_str, step_str = m.groups()
            episode, step = int(episode_str), int(step_str)
            kind: Literal["query", "chart"] = "query" if raw_kind == "code" else "chart"
            step_code = _extract_query_code(cell_code) if kind == "query" else cell_code
            steps.setdefault(episode, []).append(
                NotebookStep(episode=episode, step=step, kind=kind, code=step_code)
            )
        elif m := _ANSWER_NAME_RE.match(name):
            answers[int(m.group(1))] = _extract_markdown(cell_code)

    return [
        NotebookEpisode(
            index=episode,
            question=question,
            plan=plans.get(episode),
            steps=sorted(steps.get(episode, []), key=lambda s: s.step),
            answer=answers.get(episode),
        )
        for episode, question in sorted(questions.items())
    ]


def _extract_markdown(cell_code: str) -> str:
    match = _MARKDOWN_CELL_RE.match(cell_code.strip())
    if not match:
        raise InvalidNotebookError(Path("<markdown cell>"))
    return ast.literal_eval(match.group(1))


def _extract_query_code(cell_code: str) -> str:
    match = _QUERY_CELL_RE.match(cell_code.strip())
    if not match:
        raise InvalidNotebookError(Path("<query cell>"))
    return ast.literal_eval(match.group(1))
