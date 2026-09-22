"""`caddie notebook-open` - find or start the user's shared marimo edit
server (see `notebook/edit.py`) and open it at the workspace root, with
no specific project's file selected - marimo's own file-browser home
page for the whole `<notebooks_root>` directory, listing every project
notebook underneath it.

Backs `/caddie-open`, for a user who wants to browse the whole
workspace rather than jump straight into one project's notebook (that's
`/caddie-edit` instead, which also builds on the same shared server via
`find_running_server`/`start_server`).
"""

import argparse
import time
import webbrowser
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config
from caddie.install.notebooks import resolve_notebooks_root
from caddie.notebook.edit import EditServerError, _is_reachable, find_running_server, start_server

# How long to wait, after opening a browser tab against a freshly
# started server, before giving up on confirming it's actually
# reachable - mirrors edit.py's own session-wait padding for a cold
# --sandbox resolve.
_REACHABLE_TIMEOUT_SECONDS = 30


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "notebook-open",
        help="Find or start the user's shared marimo edit server, at the workspace root.",
    )
    parser.add_argument(
        "--config-path",
        help="Override the caddie.yaml path (mainly for testing).",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path) if args.config_path else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    notebooks_root = (
        Path(config.notebooks_root).expanduser()
        if config.notebooks_root
        else resolve_notebooks_root(None)
    )

    existing = find_running_server(notebooks_root)
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
            url = start_server(notebooks_root)
        except EditServerError as exc:
            raise SystemExit(str(exc))

        print("status: started")
        print(f"url: {url}")

    webbrowser.open(url)
    deadline = time.monotonic() + _REACHABLE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _is_reachable(url):
            print("session: active")
            return 0
        time.sleep(0.5)

    print("session: none")
    print(f"note: opened {url} in a browser but it wasn't reachable within {_REACHABLE_TIMEOUT_SECONDS}s.")
    return 0
