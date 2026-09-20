"""`caddie notebook-edit` - find or start a live `marimo edit` server
for the user's whole notebooks workspace, and print its URL plus the
specific project's file path within it.

Backs `/caddie-ask` and `/caddie-load`: those skills hand back a
rendered, static HTML export by default, but a user who wants to
interact with the notebook (rerun a cell, tweak a query by hand) needs
marimo's live editor instead.

One shared server per user, not one per project: `start_server` points
`marimo edit` at the user's whole `<notebooks_root>/<username>/`
directory rather than a single project's `notebook.py`. Pointing
`marimo edit` at a directory with `--sandbox` puts it in marimo's own
"multi-file sandbox" mode (`marimo._cli.sandbox.SandboxMode.MULTI`),
which still resolves each notebook's own PEP 723 header into its own
isolated per-notebook `uv` environment (via IPC kernels) - per-notebook
*dependency* isolation is unchanged (`.specs/requirements.md`,
Per-notebook dependency isolation) - but now under one long-running
server process instead of a new one per project. That's the fix for a
real problem: pointing at one project's file per server meant a new
`marimo edit` process (and PEP 723 sandbox resolve) for every project
ever opened, with nothing to ever stop one - they only accumulated.
Multi-file sandbox mode needs the `marimo[sandbox]` extra (`pyzmq`),
declared in caddie's own `pyproject.toml` - not in a notebook's own
header, which never needs it (see `notebook/dependencies.py`).
Re-running this command for any project reuses the one already-running
workspace server rather than starting a duplicate. Started with
`--no-token`, since it's bound to localhost for one person's own
analysis - there's no second party to authenticate against.

`data-analyst` pairs with this same server via the `marimo-pair` skill
(`.claude/skills/marimo-pair`) - its `scripts/execute-code.sh` talks
directly to marimo's own HTTP API (`/api/sessions`, `/api/kernel/execute`),
no MCP server or Claude Code tool registration involved. Since the
server now hosts every project's notebook at once, callers must target
one by its file path (`execute-code.sh --file <path>`, matching
`/api/sessions`' own `path`/`filename` fields) rather than relying on
"the one open notebook" auto-resolution. That script also needs an
active *session* for the target file, which only exists once something
has opened it in a browser - `--headless` alone never creates one.
Since `data-analyst` runs unattended, `run()` opens the project's URL
itself (`webbrowser.open`, with a `?filename=` query param selecting
which notebook inside the shared workspace to load - confirmed against
marimo's own frontend, `FilenameState.getFilename`/`setSearchParam` in
its bundled JS) whenever no session for that file exists yet, the same
way a human using `/caddie-edit` would open it by hand, and waits
briefly for the session to register before returning.
"""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.identity import resolve_username
from caddie.install.notebooks import resolve_notebooks_root
from caddie.notebook.builder import notebook_path, refresh_header

_URL_RE = re.compile(r"URL:\s*(\S+)")
_LISTEN_PORT_RE = re.compile(r":(\d+)\s*\(LISTEN\)")
# Generous: a cold start has to resolve the workspace server's own
# --sandbox environment (pyzmq etc.) before marimo can report its URL.
# Once that environment is cached, startup is back to ordinary marimo
# speed regardless of how many notebooks live under the workspace.
_START_TIMEOUT_SECONDS = 120
# How long to wait, after opening a browser tab, for marimo to report an
# active session for the target file at /api/sessions - a few seconds for
# the browser to launch and complete its websocket handshake. Padded well
# past that: on a cold start the workspace server itself may still be
# finishing its own --sandbox resolve when the browser connects, and the
# first page load/connect after that took noticeably longer than 15s in
# testing.
_SESSION_TIMEOUT_SECONDS = 30


class EditServerError(Exception):
    pass


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-edit",
        help="Find or start the user's shared marimo edit server, for one project's notebook.",
    )
    parser.add_argument("--project", required=True, help="Existing project slug to edit.")
    parser.add_argument(
        "--config-path",
        help="Override the caddie.yaml path (mainly for testing).",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path) if args.config_path else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    username = config.username or resolve_username()
    notebooks_root = (
        Path(config.notebooks_root).expanduser()
        if config.notebooks_root
        else resolve_notebooks_root(None)
    )
    user_dir = notebooks_root / username
    project_dir = user_dir / args.project
    nb_path = notebook_path(project_dir)

    if not nb_path.is_file():
        raise SystemExit(f"No project '{args.project}' under {user_dir}.")

    existing = find_running_server(user_dir)
    if existing is not None:
        print("status: already-running")
        print(f"url: {existing.url}")
        if not existing.reachable:
            print(
                "note: this server wasn't started with --no-token; if it "
                "prompts for an access token, check the terminal it was "
                "originally started from."
            )
        url = existing.url
    else:
        try:
            url = start_server(user_dir)
        except EditServerError as exc:
            raise SystemExit(str(exc))

        print("status: started")
        print(f"url: {url}")

    print(f"file: {nb_path}")

    # Only safe to rewrite the file when no kernel has it open yet: a
    # session's sandbox venv is built once, from the header on disk at
    # that time (`marimo._session.managers.ipc.KernelManager.start_kernel`)
    # - refreshing it here, before that happens, is what makes sure a
    # notebook's `--sandbox` venv (built fresh per session) resolves
    # `caddie` from this checkout instead of whatever stale/missing
    # dependency line was baked in when the notebook was first created.
    # Rewriting it once a kernel's already running for this file
    # wouldn't rebuild that kernel's already-started sandbox anyway, and
    # risks racing the running session's own writes.
    if not _has_session_for(url, nb_path) and refresh_header(project_dir, config.connector):
        print("header: refreshed")

    if ensure_session(url, nb_path):
        print("session: active")
    else:
        print("session: none")
        print(
            f"note: opened {url}?filename={urllib.parse.quote(str(nb_path))} in a "
            f"browser but no session appeared within {_SESSION_TIMEOUT_SECONDS}s - "
            "open it manually and retry before pairing."
        )
    return 0


class RunningServer:
    def __init__(self, url: str, reachable: bool) -> None:
        self.url = url
        self.reachable = reachable


def find_running_server(user_dir: Path) -> RunningServer | None:
    result = subprocess.run(["ps", "-eo", "pid,command"], capture_output=True, text=True)
    target = str(user_dir)
    for line in result.stdout.splitlines():
        if "marimo edit" not in line or target not in line:
            continue
        pid = line.split(None, 1)[0]
        port = _listen_port_for_pid(pid)
        if port is None:
            continue
        url = f"http://localhost:{port}"
        return RunningServer(url, reachable=_is_reachable(url))
    return None


def _listen_port_for_pid(pid: str) -> str | None:
    result = subprocess.run(
        ["lsof", "-aPi", "-p", pid, "-sTCP:LISTEN"], capture_output=True, text=True
    )
    for line in result.stdout.splitlines()[1:]:
        match = _LISTEN_PORT_RE.search(line)
        if match:
            return match.group(1)
    return None


def _is_reachable(url: str) -> bool:
    # A server started with a token redirects an unauthenticated GET to
    # `/auth/login`; urlopen follows that redirect and still returns
    # 200 for the login page itself, so status alone can't tell the
    # two cases apart - check where the request actually landed.
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200 and "/auth/login" not in resp.geturl()
    except Exception:
        return False


def _active_sessions(url: str) -> dict:
    try:
        with urllib.request.urlopen(f"{url}/api/sessions", timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def _has_session_for(url: str, nb_path: Path) -> bool:
    target = str(nb_path)
    for info in _active_sessions(url).values():
        if info.get("path") == target or info.get("filename") == target:
            return True
    return False


def ensure_session(url: str, nb_path: Path) -> bool:
    """True if a browser session is already attached to `nb_path` on
    this (possibly shared, multi-notebook) server; if not, opens that
    file in a browser (the same thing a human running `/caddie-edit`
    would do) and waits briefly for its session to register."""
    if _has_session_for(url, nb_path):
        return True

    webbrowser.open(f"{url}?filename={urllib.parse.quote(str(nb_path))}")
    deadline = time.monotonic() + _SESSION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _has_session_for(url, nb_path):
            return True
        time.sleep(0.5)
    return False


def start_server(user_dir: Path) -> str:
    log_path = user_dir / ".marimo_edit.log"
    log_fh = open(log_path, "w")
    try:
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "marimo",
                "edit",
                str(user_dir),
                "--headless",
                "--no-token",
                "--sandbox",
            ],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_fh.close()

    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        text = log_path.read_text()
        match = _URL_RE.search(text)
        if match:
            return match.group(1)
        time.sleep(0.25)

    raise EditServerError(
        f"marimo edit did not report a URL within {_START_TIMEOUT_SECONDS}s; "
        f"see {log_path}"
    )
