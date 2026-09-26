"""Pushes a rendered `costs` cell into a project's live marimo kernel,
without any LLM involved - `caddie track-update` runs as a `Stop` hook
(see `caddie.cost.tracker`), not inside an agent turn, so it has to
drive the kernel the same way `marimo-pair`'s `execute-code.sh` does:
talk to marimo's own HTTP API directly.

Reuses `caddie.notebook.edit`'s server/session discovery rather than
reimplementing it - this module only adds the one thing that skill
script provides that a plain Python caller needs: submitting code to
`/api/kernel/execute` and reading its result.

If the notebook isn't currently paired (no live session for it), that's
not an error here - the caller falls back to leaving the sidecar state
and `.transcripts/` copy updated, and the next successful update
reflects the full accumulated total.
"""

import json
import urllib.request
from pathlib import Path

from caddie.notebook.edit import active_sessions, find_running_server

_EXECUTE_TIMEOUT_SECONDS = 30

# Written by the notebook-improvements convention `marimo-pair` itself
# documents (`create_cell`/`edit_cell`/`run_cell`/`delete_cell`, all
# queued inside `cm.get_context()`). Verify this against a live
# `help(cm)` if marimo's private `_code_mode` API has moved since this
# was written - the skill's own docs call that API "PRIVATE, UNSTABLE".
_UPDATE_COSTS_CELL_TEMPLATE = """
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    existing_id = None
    for cid, cell in ctx.cells.items():
        if cell.name == "costs":
            existing_id = cid
            break
    if existing_id is not None:
        ctx.delete_cell(existing_id)
    new_id = ctx.create_cell({code!r}, name="costs", hide_code=False)
    ctx.run_cell(new_id)
"""


class KernelUnavailable(Exception):
    pass


def session_for_notebook(notebooks_root: Path, notebook_path: Path) -> tuple[str, str] | None:
    """(server_url, marimo_session_id) for `notebook_path` if a browser
    session is already attached to it on the shared workspace server -
    None if there's no running server, or no session for this file."""
    server = find_running_server(notebooks_root)
    if server is None:
        return None

    target = str(notebook_path)
    for session_id, info in active_sessions(server.url).items():
        if info.get("path") == target or info.get("filename") == target:
            return server.url, session_id
    return None


def _execute(url: str, session_id: str, code: str) -> None:
    body = json.dumps({"code": code}).encode()
    req = urllib.request.Request(
        f"{url.rstrip('/')}/api/kernel/execute",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Marimo-Session-Id": session_id,
        },
    )
    with urllib.request.urlopen(req, timeout=_EXECUTE_TIMEOUT_SECONDS) as resp:
        raw = resp.read().decode(errors="replace")

    success = True
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        if event == "done" and data:
            payload = json.loads(data)
            success = payload.get("success", True) is not False

    if not success:
        raise KernelUnavailable(f"marimo kernel execution failed: {raw[-2000:]}")


def update_costs_cell(notebooks_root: Path, notebook_path: Path, cell_code: str) -> bool:
    """Push `cell_code` as the notebook's `costs` cell (delete +
    recreate, so it always ends up last). Returns False (no exception)
    if the notebook simply isn't paired right now."""
    session = session_for_notebook(notebooks_root, notebook_path)
    if session is None:
        return False

    url, session_id = session
    code = _UPDATE_COSTS_CELL_TEMPLATE.format(code=cell_code)
    _execute(url, session_id, code)
    return True
