"""CLI entry points behind cost tracking - none of them called
directly by a skill. Both are wired up as Claude Code hooks
(`hooks/hooks.json`) and read their input from stdin the way every
hook does, so tracking runs deterministically regardless of what the
agent did or didn't remember to do:

- `track-observe`: a `PostToolUse` hook matching `Bash`. Watches for
  the two commands that open or create a project
  (`caddie notebook-start`, `caddie notebook-edit`) and reads the
  notebook path either already prints to stdout - no skill instruction
  to call anything cost-related needed at all. This is what marks a
  session as "working on project X" (see `caddie.cost.tracker`'s
  session marker).
- `track-update`: a `Stop` hook. Folds new session usage into the
  tracked project's cost and refreshes its `costs` cell, and (best
  effort, in the background) relaunches `notebook-export` if the
  project's PDF is behind its notebook - see `_launch_background_export`.

`track-start` still exists as a manual/scriptable equivalent of what
`track-observe` now does automatically - useful for testing, or a
future caller that doesn't go through `notebook-start`/`notebook-edit`.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.cost import pricing, tracker
from caddie.cost.kernel import update_costs_cell
from caddie.install.notebooks import find_project_dir, resolve_notebooks_root
from caddie.notebook.builder import notebook_path
from caddie.notebook.export import pdf_path

# `notebook-start` prints `notebook: <path>`, `notebook-edit` prints
# `file: <path>` (both `notebook/start.py` and `notebook/edit.py`) -
# either line gives the notebook's absolute path, whose parent is the
# project directory.
_NOTEBOOK_PATH_RE = re.compile(r"^(?:notebook|file):\s*(.+)$", re.MULTILINE)

_TRACKED_COMMANDS = ("caddie notebook-start", "caddie notebook-edit")


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    start = subparsers.add_parser(
        "track-start",
        help="Mark this Claude Code session as working on `--project`, for cost tracking. "
        "Manual equivalent of what `track-observe` does automatically.",
    )
    start.add_argument("--project", required=True, help="Existing project slug.")
    start.add_argument("--config-path", help="Override the caddie.yaml path (mainly for testing).")
    start.set_defaults(handler=run_track_start)

    observe = subparsers.add_parser(
        "track-observe",
        help="PostToolUse-hook entry point: notice a `caddie notebook-start`/"
        "`notebook-edit` Bash call and mark this session as tracking that project. "
        "Reads hook JSON from stdin.",
    )
    observe.set_defaults(handler=run_track_observe)

    update = subparsers.add_parser(
        "track-update",
        help="Stop-hook entry point: fold new session usage into the tracked "
        "project's cost, and refresh its `costs` cell. Reads hook JSON from stdin.",
    )
    update.add_argument("--config-path", help="Override the caddie.yaml path (mainly for testing).")
    update.set_defaults(handler=run_track_update)


def _notebooks_root(config_path: str | None) -> Path:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    config = load_config(path)
    return (
        Path(config.notebooks_root).expanduser()
        if config.notebooks_root
        else resolve_notebooks_root(None)
    )


def _start_tracking(session_id: str, project_dir: Path) -> None:
    tracker.write_marker(session_id, project_dir)
    # Best-effort, network-bound - deliberately not done in
    # `track-update` (the `Stop` hook), which fires every turn and must
    # stay fast and offline-safe. Once per episode/step - which is how
    # often `notebook-start`/`notebook-edit` (and so `track-observe`)
    # run - is an acceptable place for a few seconds' pricing refresh.
    pricing.refresh()


def run_track_start(args: argparse.Namespace) -> int:
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session_id:
        print("track-start: no CLAUDE_CODE_SESSION_ID in the environment", file=sys.stderr)
        return 1

    notebooks_root = _notebooks_root(args.config_path)
    project_dir = find_project_dir(notebooks_root, args.project)
    if project_dir is None:
        raise SystemExit(f"No project '{args.project}' under {notebooks_root}.")

    _start_tracking(session_id, project_dir)
    print(f"tracking: {project_dir}")
    return 0


def run_track_observe(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0  # Matcher in hooks.json already filters this, but stay defensive.

    command = (payload.get("tool_input") or {}).get("command", "")
    if not any(marker in command for marker in _TRACKED_COMMANDS):
        return 0

    session_id = payload.get("session_id")
    stdout = (payload.get("tool_response") or {}).get("stdout", "")
    match = _NOTEBOOK_PATH_RE.search(stdout)
    if not session_id or not match:
        return 0  # The command errored, or printed something unexpected - no-op.

    project_dir = Path(match.group(1).strip()).parent
    _start_tracking(session_id, project_dir)
    return 0


def _export_stale(project_dir: Path) -> bool:
    nb_path = notebook_path(project_dir)
    out_path = pdf_path(project_dir)
    if not out_path.is_file():
        return True
    return nb_path.stat().st_mtime > out_path.stat().st_mtime


def _caddie_bin() -> str:
    """Resolve the installed `caddie` console-script the same way
    `hooks/hooks.json` does - `caddie` isn't runnable via `python -m`
    (no `__main__.py`; it's a `uv tool install`ed entry point), so a
    background relaunch has to find that script on PATH, falling back
    to the same default `uv tool install` location the hook shells out
    to when PATH lookup fails (e.g. a non-login subprocess env)."""
    return shutil.which("caddie") or str(Path.home() / ".local" / "bin" / "caddie")


def _launch_background_export(project_dir: Path, config_path: str | None) -> None:
    """Fire-and-forget `caddie notebook-export`, launched from the
    `Stop` hook so a project's PDF stays in sync with its notebook
    after each episode/explore turn - without making `track-update`
    (which fires every turn) wait on a `--webpdf` render.

    Detached (`start_new_session=True`, all three standard streams
    redirected) so the child outlives this hook's own short-lived
    process rather than being torn down with it, the same way
    `notebook/edit.py`'s `start_server` detaches the shared marimo
    server."""
    command = [_caddie_bin(), "notebook-export", "--project", project_dir.name]
    if config_path:
        command += ["--config-path", config_path]

    log_path = tracker.STATE_DIR / "hooks.log"
    tracker.STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "a")
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_fh.close()


def run_track_update(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    session_id = payload.get("session_id")
    transcript_path_raw = payload.get("transcript_path")
    if not session_id or not transcript_path_raw:
        return 0

    project_dir = tracker.read_marker(session_id)
    if project_dir is None:
        return 0  # This session isn't tracking a caddie project right now.

    transcript_path = Path(transcript_path_raw)
    result = tracker.update_project(project_dir, session_id, transcript_path)

    try:
        notebooks_root = _notebooks_root(args.config_path)
        nb_path = notebook_path(project_dir)
        cell_code = tracker.costs_cell_code(result.state.costs)
        update_costs_cell(notebooks_root, nb_path, cell_code)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see below.
        # Accounting and the transcript copy already landed (above) -
        # only the live cell push is best-effort. Anything can go wrong
        # here (no caddie.yaml, no running kernel, a marimo API change)
        # and none of it should ever crash a `Stop` hook or block the
        # session it's attached to; the next successful update reflects
        # the full accumulated total regardless.
        print(f"track-update: costs cell not updated ({exc})", file=sys.stderr)

    try:
        if _export_stale(project_dir):
            _launch_background_export(project_dir, args.config_path)
    except Exception as exc:  # noqa: BLE001 - same reasoning as above.
        print(f"track-update: pdf export not launched ({exc})", file=sys.stderr)

    return 0
