"""Per-project metadata that lives alongside a notebook but isn't part
of its cells: the connector the project was created with, and each
cell group's last execution stats (row count, columns).

A notebook always re-runs against the connector it was created with,
not whatever happens to be active in `caddie.yaml` at load time (see
requirements.md's `/caddie-load`), so that has to be recorded somewhere
outside the notebook's own reactive cell code. The per-group stats
exist so `/caddie-load` can report what changed since the last run
without marimo having to persist output between sessions.

Kept as a small sidecar JSON file rather than folded into the notebook
itself, since none of it is meant to be hand-edited or diffed the way
cell content is.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STATE_FILENAME = ".caddie_project.json"


@dataclass
class GroupStats:
    row_count: int | None
    columns: list[str]


@dataclass
class ProjectState:
    connector: str
    connector_settings: dict[str, Any] = field(default_factory=dict)
    groups: dict[str, GroupStats] = field(default_factory=dict)


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
        groups={k: GroupStats(**v) for k, v in raw.get("groups", {}).items()},
    )


def save_state(project_dir: Path, state: ProjectState) -> None:
    path = state_path(project_dir)
    path.write_text(
        json.dumps(
            {
                "connector": state.connector,
                "connector_settings": state.connector_settings,
                "groups": {k: asdict(v) for k, v in state.groups.items()},
            },
            indent=2,
        )
    )
