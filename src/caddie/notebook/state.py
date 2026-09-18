"""Per-project metadata that lives alongside a notebook but isn't part
of its cells: the connector the project was created with, and each
step's last execution stats (kind, row count, columns).

A notebook always re-runs against the connector it was created with,
not whatever happens to be active in `caddie.yaml` at load time (see
requirements.md's `/caddie-load`), so that has to be recorded somewhere
outside the notebook's own reactive cell code. The per-step stats exist
so `/caddie-load` can report what changed since the last run without
marimo having to persist output between sessions.

Plan and answer text are deliberately never stored here - they live
only in the notebook's own cells, since (unlike execution stats) they
are authored content, not something to hand-edit or diff.

Kept as a small sidecar JSON file rather than folded into the notebook
itself, since none of it is meant to be hand-edited or diffed the way
cell content is.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

STATE_FILENAME = ".caddie_project.json"


@dataclass
class StepStats:
    kind: Literal["query", "chart"]
    row_count: int | None = None
    columns: list[str] = field(default_factory=list)


@dataclass
class ProjectState:
    connector: str
    connector_settings: dict[str, Any] = field(default_factory=dict)
    steps: dict[str, StepStats] = field(default_factory=dict)


def state_path(project_dir: Path) -> Path:
    return project_dir / STATE_FILENAME


def load_state(project_dir: Path) -> ProjectState | None:
    path = state_path(project_dir)
    if not path.is_file():
        return None

    raw = json.loads(path.read_text())
    return ProjectState(
        connector=raw["connector"],
        connector_settings=raw.get("connector_settings", {}),
        steps={k: StepStats(**v) for k, v in raw.get("steps", {}).items()},
    )


def save_state(project_dir: Path, state: ProjectState) -> None:
    path = state_path(project_dir)
    path.write_text(
        json.dumps(
            {
                "connector": state.connector,
                "connector_settings": state.connector_settings,
                "steps": {k: asdict(v) for k, v in state.steps.items()},
            },
            indent=2,
        )
    )
