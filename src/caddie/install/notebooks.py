"""Resolves and creates the notebooks root.

Per requirements.md Storage: default root is `~/caddie/notebooks`, user
overridable via `--notebooks-root`. Projects live directly under this
root (`<root>/<project-slug>/`) - no per-user subfolder, since
`~/caddie/notebooks` is already scoped to the single OS user who owns
`~` (see requirements-plugin.md, "Dropping identity resolution").
"""

from pathlib import Path

DEFAULT_NOTEBOOKS_ROOT = Path.home() / "caddie" / "notebooks"


def resolve_notebooks_root(override: str | None) -> Path:
    return Path(override).expanduser() if override else DEFAULT_NOTEBOOKS_ROOT


def ensure_notebooks_dir(notebooks_root: Path) -> Path:
    notebooks_root.mkdir(parents=True, exist_ok=True)
    return notebooks_root
