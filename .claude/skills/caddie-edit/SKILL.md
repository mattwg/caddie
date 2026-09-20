---
name: caddie-edit
description: Open an existing Caddie analysis project in a live marimo edit server — reuses an already-running server for that notebook instead of starting a duplicate, and opens it in marimo's read-only "Present" app view by default (code hidden, outputs and data tables fully interactive, since a live kernel is behind it). Trigger on "/caddie-edit <project>", or when a user asks to edit, tweak, or interact with a notebook that /caddie-ask or /caddie-load already produced (the rendered HTML those hand back is static and can't render live data previews).
---

# /caddie-edit <project>

`/caddie-ask` and `/caddie-load` hand back a rendered, static HTML
export by default — enough to read the answer, but it's a one-shot
export with no running kernel behind it, so a `mo.ui.table`/dataframe
output degrades to an inert "Preview data" button that can't actually
fetch rows. This skill opens the project's live marimo editor instead,
which has a real kernel to answer that request: checking for and
running the server itself lives in `caddie notebook-edit`, which either
finds an already-running server for that exact notebook or starts a new
one; this skill's job is to invoke it and open the URL it prints — by
default landing on marimo's "Present" view, not the raw editor.

The server is started with `--sandbox`: marimo runs the notebook in a
`uv`-managed environment built from that notebook's own dependency
header, isolated from caddie's own shared venv. First launch for a
given notebook can take noticeably longer (up to ~2 minutes) while `uv`
resolves and installs that environment; later launches reuse `uv`'s
cache and are fast. If the notebook needs a package beyond caddie's own
baseline, that's `/caddie-add-dependency`, not editing caddie's own
`pyproject.toml`.

## Invoking the CLI

The command below assumes `caddie` is on `PATH`. If the working
directory is a checkout of the Caddie project itself (look for a
`pyproject.toml` with `name = "caddie"` at or above the working
directory), the `caddie` entry point only exists inside that project's
own virtualenv — running it bare will fail with `command not found`.
In that case, prefix it with `uv run`, e.g. `uv run caddie
notebook-edit ...`. Check for this once at the start rather than
discovering it after a failed call.

## Steps

1. Resolve the project slug — the argument given, or the active
   project from earlier in the conversation (`/caddie-ask` or
   `/caddie-load`) if none was given. If neither is available, ask the
   user which project, or point them at `/caddie-list`.

2. Run:

   ```
   caddie notebook-edit --project <slug>
   ```

   `status: already-running` means a server for this exact notebook is
   already up and its URL is being reused; `status: started` means a
   new one was just launched (headless, no browser opened by marimo
   itself — this skill opens it below instead).

3. Open the printed `url`, with `?view-as=present` appended (e.g.
   `http://localhost:2718/?view-as=present`), for the user — this is a
   real marimo query parameter, not a separate server mode: it's the
   same edit-mode server and websocket session, just landing the
   browser on marimo's "Present" view (code hidden, outputs and data
   tables rendered live) instead of the code-visible editor. The user
   can still switch back to the editor from within the page using
   marimo's own view toggle if they want to see or change the code —
   this only picks which view loads first. In the Claude Code desktop
   app (Browser pane available), call `preview_start` with `url:
   <url>?view-as=present` directly — no `.claude/launch.json` entry is
   needed or wanted here. `caddie notebook-edit` already owns the
   server's lifecycle (finding an existing one vs. starting a new one,
   on its own port); a launch.json config that tries to start its own
   copy (e.g. a hardcoded `--port`) only adds a second, worse way to do
   the same thing, and risks colliding with an unrelated process
   already on that port or going stale and pointing at a notebook that
   no longer exists. Outside the desktop app, run `open
   "<url>?view-as=present"` (macOS) via a shell command instead — plain
   CLI chat can't render a URL as clickable.

4. Relay to the user:
   - Whether a new server was started or an existing one reused.
   - The URL (with `?view-as=present`) as plain text as a fallback in
     case opening it failed, and a one-line note that the code-visible
     editor is one click away in the page's own view toggle if they
     want to edit a cell.
   - If the command printed a `note:` line (an existing server that
     wasn't started with `--no-token`), pass that caveat along
     verbatim — the user may need a token from wherever they first
     started it.

## Caveat: don't edit the notebook file while its live server is open

A running marimo edit server keeps its own in-memory copy of the
notebook and can write that copy back over the file on disk (e.g. on
autosave, or when a browser tab connects/reconnects) — even if the
file was changed on disk in the meantime by something else. Concretely:
if you make further programmatic edits to a project's `notebook.py`
after its edit server is already running — another `caddie
notebook-step`/`notebook-answer` call, or a direct file edit — and then
open or reconnect to that same server, it can silently clobber your
edits with its stale prior state.

So: treat "server running" and "editing the file outside marimo" as
mutually exclusive for a given notebook. If you need to make more
programmatic edits to a notebook that already has a live server open,
stop that server first (find its PID via the port `notebook-edit`
printed, e.g. `lsof -nP -iTCP:<port> -sTCP:LISTEN`, and kill it), make
the edits, then start a fresh server with `caddie notebook-edit` again.
Don't assume a previously opened browser tab is still showing current
content once the file has changed underneath it.
