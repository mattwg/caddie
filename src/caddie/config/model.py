from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaddieConfig:
    skills: list[str]
    skill_repo: str
    connector: str
    connector_settings: dict[str, Any] = field(default_factory=dict)
    context: str | None = None
    notebooks_root: str | None = None
    skill_repo_path: str | None = None
    config_source: str | None = None
