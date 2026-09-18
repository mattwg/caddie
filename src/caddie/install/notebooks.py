"""Resolves and creates the user's notebooks root.

Per requirements.md Storage: default root is `~/caddie/notebooks`, user
overridable via `--notebooks-root`; the per-user project folder is
`<root>/<username>/`.
"""

from pathlib import Path

DEFAULT_NOTEBOOKS_ROOT = Path.home() / "caddie" / "notebooks"


def resolve_notebooks_root(override: str | None) -> Path:
    return Path(override).expanduser() if override else DEFAULT_NOTEBOOKS_ROOT


def ensure_user_notebooks_dir(notebooks_root: Path, username: str) -> Path:
    project_dir = notebooks_root / username
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir
