"""Resolves the org skill repo (a git URL or an already-local path) to a
local directory Caddie can read skills and caddie.default.yaml from."""

import subprocess
from pathlib import Path


def resolve_skill_repo(skill_repo: str, clone_root: Path) -> Path:
    """Return a local path for skill_repo, cloning it if needed.

    A skill_repo that already exists on disk (the common case for test
    fixtures, or a repo the user already has checked out) is used
    as-is. Otherwise it's treated as a git URL and cloned under
    clone_root; re-running with the same skill_repo reuses the
    existing clone rather than cloning again.
    """
    local_candidate = Path(skill_repo).expanduser()
    if local_candidate.exists():
        return local_candidate.resolve()

    dest = clone_root / _slug(skill_repo)
    if dest.is_dir():
        return dest

    clone_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", skill_repo, str(dest)], check=True)
    return dest


def _slug(skill_repo: str) -> str:
    name = skill_repo.rstrip("/").rsplit("/", 1)[-1]
    return name[: -len(".git")] if name.endswith(".git") else name


def pull_skill_repo(path: Path) -> None:
    """`git pull` the resolved skill_repo clone, if it's actually a git repo.

    A skill_repo pointed at a plain local directory (e.g. test
    fixtures, or a path the user manages themselves) isn't something
    `caddie update` should try to pull. Checking the repo *toplevel*
    (not just "is inside a work tree") also correctly skips a fixture
    directory that merely happens to live inside caddie core's own
    git repo.
    """
    toplevel = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if toplevel.returncode != 0:
        return
    if Path(toplevel.stdout.strip()).resolve() != path.resolve():
        return
    subprocess.run(["git", "-C", str(path), "pull", "--ff-only"], check=True)
