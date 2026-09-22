"""Resolves and creates the notebooks root.

Per requirements.md Storage: default root is `~/caddie/notebooks`, user
overridable via `--notebooks-root`. Projects live under a date
partition of this root (`<root>/<year>/Q<quarter>/<month>/<date>/
<project-slug>/`) - no per-user subfolder, since `~/caddie/notebooks`
is already scoped to the single OS user who owns `~` (see
requirements-plugin.md, "Dropping identity resolution").

The date partition groups projects by when they were started, purely
for browsability on disk (a year of daily analysis without it becomes
one flat folder of hundreds of slugs) - it plays no role in lookup.
Every other command addresses a project by its bare slug alone
(`--project <slug>`, matching what `notebook-start` and `list` print),
so `find_project_dir` searches the whole tree for it rather than
requiring the caller to know or reconstruct its partition.
"""

from datetime import date
from pathlib import Path

DEFAULT_NOTEBOOKS_ROOT = Path.home() / "caddie" / "notebooks"


def resolve_notebooks_root(override: str | None) -> Path:
    return Path(override).expanduser() if override else DEFAULT_NOTEBOOKS_ROOT


def ensure_notebooks_dir(notebooks_root: Path) -> Path:
    notebooks_root.mkdir(parents=True, exist_ok=True)
    return notebooks_root


def partition_dir(notebooks_root: Path, when: date) -> Path:
    """The year/quarter/month/date folder a project started `when` lives under."""
    quarter = (when.month - 1) // 3 + 1
    return notebooks_root / str(when.year) / f"Q{quarter}" / f"{when.month:02d}" / when.isoformat()


def existing_slugs(notebooks_root: Path) -> set[str]:
    """Every project slug already in use, anywhere under the (partitioned) root."""
    if not notebooks_root.is_dir():
        return set()
    return {nb.parent.name for nb in notebooks_root.rglob("notebook.py")}


def find_project_dir(notebooks_root: Path, slug: str) -> Path | None:
    """The directory for an existing project, wherever its date partition put it."""
    for candidate in notebooks_root.rglob(slug):
        if candidate.is_dir() and (candidate / "notebook.py").is_file():
            return candidate
    return None
