"""`caddie notebook-edit` - find or start a live `marimo edit` server
for a project's notebook, and print its URL.

Backs `/caddie-ask` and `/caddie-load`: those skills hand back a
rendered, static HTML export by default, but a user who wants to
interact with the notebook (rerun a cell, tweak a query by hand) needs
marimo's live editor instead. Re-running this command for the same
project reuses an already-running server rather than starting a
duplicate on another port. Started servers use `--no-token`, since
they're bound to localhost for one person's own analysis - there's no
second party to authenticate against.
"""

import argparse
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.identity import resolve_username
from caddie.install.notebooks import resolve_notebooks_root
from caddie.notebook.builder import notebook_path

_URL_RE = re.compile(r"URL:\s*(\S+)")
_LISTEN_PORT_RE = re.compile(r":(\d+)\s*\(LISTEN\)")
_START_TIMEOUT_SECONDS = 15


class EditServerError(Exception):
    pass


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-edit",
        help="Find or start a marimo edit server for a project's notebook.",
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

    existing = find_running_server(nb_path)
    if existing is not None:
        print("status: already-running")
        print(f"url: {existing.url}")
        if not existing.reachable:
            print(
                "note: this server wasn't started with --no-token; if it "
                "prompts for an access token, check the terminal it was "
                "originally started from."
            )
        return 0

    try:
        url = start_server(nb_path)
    except EditServerError as exc:
        raise SystemExit(str(exc))

    print("status: started")
    print(f"url: {url}")
    return 0


class RunningServer:
    def __init__(self, url: str, reachable: bool) -> None:
        self.url = url
        self.reachable = reachable


def find_running_server(nb_path: Path) -> RunningServer | None:
    result = subprocess.run(["ps", "-eo", "pid,command"], capture_output=True, text=True)
    target = str(nb_path)
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


def start_server(nb_path: Path) -> str:
    log_path = nb_path.parent / ".marimo_edit.log"
    log_fh = open(log_path, "w")
    try:
        subprocess.Popen(
            [sys.executable, "-m", "marimo", "edit", str(nb_path), "--headless", "--no-token"],
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
