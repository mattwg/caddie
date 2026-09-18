"""Verifies that named analytics skills are present and loadable.

An analytics skill is a Claude Code skill, not a Python interface —
Caddie core never invokes one directly (that happens via the Skill
tool inside a live Claude Code session). What Caddie core does own is
confirming a named skill actually exists in the skill repo before
anything tries to use it, and parsing whatever that skill returns
(see parser.py).
"""

from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

_yaml = YAML(typ="safe")


class SkillNotFoundError(Exception):
    def __init__(self, name: str, available: list[str]) -> None:
        available_str = ", ".join(sorted(available)) if available else "none"
        super().__init__(
            f"No skill named '{name}' was found under the skill repo. "
            f"Available: {available_str}."
        )
        self.name = name
        self.available = available


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    path: Path


def _skill_dirs(skill_repo_path: Path) -> dict[str, Path]:
    if not skill_repo_path.is_dir():
        return {}
    return {
        d.name: d
        for d in skill_repo_path.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    }


def _read_frontmatter(skill_md_path: Path) -> dict:
    text = skill_md_path.read_text()
    if not text.startswith("---"):
        raise ValueError(f"{skill_md_path} has no YAML frontmatter.")
    _, frontmatter, _ = text.split("---", 2)
    return _yaml.load(frontmatter) or {}


def verify_skill(name: str, skill_repo_path: Path) -> SkillInfo:
    """Confirm a single skill by name is present and loadable.

    Raises SkillNotFoundError if it isn't installed under skill_repo_path.
    """
    available = _skill_dirs(skill_repo_path)
    if name not in available:
        raise SkillNotFoundError(name, list(available.keys()))

    skill_dir = available[name]
    frontmatter = _read_frontmatter(skill_dir / "SKILL.md")
    return SkillInfo(
        name=frontmatter.get("name", name),
        description=frontmatter.get("description", ""),
        path=skill_dir,
    )


def verify_skills(names: list[str], skill_repo_path: Path) -> list[SkillInfo]:
    """Confirm every named skill is present and loadable.

    Used by `caddie install`'s verification step; does no selection
    between skills, just confirms each one named in caddie.yaml exists.
    """
    return [verify_skill(name, skill_repo_path) for name in names]
