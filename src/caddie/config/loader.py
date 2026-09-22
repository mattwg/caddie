"""Reads/writes the user's local ~/.caddie/caddie.yaml.

There is a single config file, hand-edited and machine-written, so
writes must go through a round-trip-safe YAML load/dump that preserves
comments and formatting rather than a naive full rewrite.
"""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from caddie.config.errors import ConfigValidationError
from caddie.config.model import CaddieConfig

DEFAULT_CONFIG_PATH = Path.home() / ".caddie" / "caddie.yaml"

_KNOWN_KEYS = {
    "skills",
    "skill_repo",
    "connector",
    "context",
    "notebooks_root",
    "skill_repo_path",
    "config_source",
}
_REQUIRED_KEYS = ("skills", "skill_repo", "connector")

# Keys a pre-plugin caddie.yaml may still carry that are no longer part
# of the config shape. Stripped on load rather than left to fall into
# connector_settings (where they'd get passed as an unexpected kwarg to
# a connector's constructor) and dropped for good the next time this
# file is saved.
_DROPPED_LEGACY_KEYS = {"username"}

# Every key that belongs to caddie's own config shape (current or
# legacy) rather than to a connector. An org config yaml reuses the
# same key names for skill_repo/skills/connector/etc, plus its own
# caddie_source (consumed by /caddie:install itself, before caddie
# exists, to know what to `uv tool install`) — none of these should
# ever land in connector_settings, whatever else the org config yaml
# happens to contain.
NON_CONNECTOR_KEYS = _KNOWN_KEYS | _DROPPED_LEGACY_KEYS | {"caddie_source"}

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 4096  # don't line-wrap long scalars like skill_repo_path


def _new_yaml_map() -> Any:
    yaml = YAML()
    return yaml.load("{}\n")


def _validate(raw: Any, path: Path) -> None:
    if not isinstance(raw, dict):
        raise ConfigValidationError(f"{path} does not contain a YAML mapping.")

    missing = [k for k in _REQUIRED_KEYS if not raw.get(k)]
    if missing:
        raise ConfigValidationError(
            f"{path} is missing required field(s): {', '.join(missing)}."
        )

    skills = raw["skills"]
    if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
        raise ConfigValidationError(
            f"{path}'s 'skills' field must be a list of skill names."
        )


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> CaddieConfig:
    if not path.is_file():
        raise ConfigValidationError(
            f"No caddie.yaml found at {path}. Run /caddie-install first."
        )

    with path.open() as f:
        raw = _yaml.load(f)

    if raw is None:
        raise ConfigValidationError(f"{path} is empty.")

    _validate(raw, path)

    connector_settings = {
        k: raw[k] for k in raw if k not in _KNOWN_KEYS and k not in _DROPPED_LEGACY_KEYS
    }

    return CaddieConfig(
        skills=list(raw["skills"]),
        skill_repo=raw["skill_repo"],
        connector=raw["connector"],
        connector_settings=connector_settings,
        context=raw.get("context"),
        notebooks_root=raw.get("notebooks_root"),
        skill_repo_path=raw.get("skill_repo_path"),
        config_source=raw.get("config_source"),
    )


def save_config(config: CaddieConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Write config back to disk.

    If path already exists, its existing formatting/comments are
    preserved and only the changed fields are updated in place. If it
    doesn't exist yet, a fresh file is created.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file():
        with path.open() as f:
            raw = _yaml.load(f) or CommentedMap()
    else:
        raw = _new_yaml_map()

    raw["skills"] = list(config.skills)
    raw["skill_repo"] = config.skill_repo
    raw["connector"] = config.connector

    for key in ("context", "notebooks_root", "skill_repo_path", "config_source"):
        value = getattr(config, key)
        if value is not None:
            raw[key] = value
        elif key in raw:
            del raw[key]

    for key, value in config.connector_settings.items():
        raw[key] = value

    for key in _DROPPED_LEGACY_KEYS:
        if key in raw:
            del raw[key]

    with path.open("w") as f:
        _yaml.dump(raw, f)
