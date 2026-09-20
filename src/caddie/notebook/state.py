"""Per-project metadata that lives alongside a notebook but isn't part
of its cells: the connector the project was created with.

A notebook always re-runs against the connector it was created with,
not whatever happens to be active in `caddie.yaml` at load time (see
requirements.md's `/caddie-load`), so that has to be recorded somewhere
outside the notebook's own reactive cell code.

Plan and answer text are deliberately never stored here - they live
only in the notebook's own cells, since they are authored content, not
something to hand-edit.

Kept as a small sidecar JSON file rather than folded into the notebook
itself, since none of it is meant to be hand-edited the way cell
content is.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STATE_FILENAME = ".caddie_project.json"


@dataclass
class ProjectState:
    connector: str
    connector_settings: dict[str, Any] = field(default_factory=dict)


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
    )


def save_state(project_dir: Path, state: ProjectState) -> None:
    path = state_path(project_dir)
    path.write_text(
        json.dumps(
            {
                "connector": state.connector,
                "connector_settings": state.connector_settings,
            },
            indent=2,
        )
    )
