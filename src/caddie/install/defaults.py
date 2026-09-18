"""Reads an org's optional caddie.default.yaml.

Seeds install prompts with known-good starting values (skills,
connector, connector settings) so a new user isn't guessing things
like a Databricks workspace host. Never read again after install."""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

_yaml = YAML(typ="safe")


def load_defaults(skill_repo_path: Path) -> dict[str, Any]:
    defaults_path = skill_repo_path / "caddie.default.yaml"
    if not defaults_path.is_file():
        return {}
    with defaults_path.open() as f:
        data = _yaml.load(f)
    return data or {}
