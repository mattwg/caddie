---
name: open
description: Open Marimo on the whole notebooks workspace — no specific project selected, just marimo's own file-browser home page listing every project notebook under notebooks_root. Trigger on "/caddie:open".
---

# /caddie:open

Reuses the same shared marimo edit server as `/caddie:edit` and
`/caddie:load` (one server for the whole workspace, not one per
project), but opens it at the workspace root instead of jumping into a
specific project's notebook — useful when the user just wants to browse
what's there rather than resume one project.

## Invoking the CLI

The command below assumes `caddie` is already on `PATH` (installed
separately from this plugin, e.g. via `uv tool install caddie`). If it
fails with `command not found`, point the user at `/caddie:install`
rather than guessing at a workaround.

## Steps

1. Run:

   ```
   caddie notebook-open
   ```

   `status: already-running` means the shared workspace server is
   already up and its URL is being reused; `status: started` means it
   was just launched for the first time (first launch can take up to
   ~2 minutes while `uv` resolves the `--sandbox` environment; later
   launches reuse `uv`'s cache and are fast). The command opens the
   server's base URL in a browser itself.

2. In the Claude Code desktop app (Browser pane available), call
   `preview_start` with the printed `url` directly instead of relying
   on the CLI's own browser-open — no `.claude/launch.json` entry is
   needed or wanted here, since `caddie notebook-open` already owns the
   server's lifecycle.

3. Relay to the user:
   - Whether a new server was started or an existing one reused.
   - The URL as plain text as a fallback in case opening it failed.
   - If the command printed a `note:` line (an existing server that
     wasn't started with `--no-token`, or the browser tab wasn't
     reachable within the timeout), pass that caveat along verbatim.

## Caveat: never hand-edit a `notebook.py` while its server is open

A live marimo server can overwrite a notebook's file on disk with its
own in-memory copy at any time (autosave, browser reconnect). If you
edit one of the workspace's notebook files directly while the server
has it open, your edit can get silently wiped out.
