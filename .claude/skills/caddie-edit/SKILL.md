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
finds an already-running server or starts a new one; this skill's job
is to invoke it and open the URL it prints — by default landing on
marimo's "Present" view, not the raw editor.

The server is shared across every one of your projects, not one per
notebook: `notebook-edit` points marimo at your whole notebooks
workspace directory with `--sandbox`, which still resolves each
notebook's own dependency header into its own isolated `uv`-managed
environment (marimo's own "multi-file sandbox" mode), just under one
long-running process instead of a new one per project. First launch of
the workspace server can take noticeably longer (up to ~2 minutes)
while `uv` resolves and installs that environment; later launches (for
any project) reuse `uv`'s cache and are fast, and opening a second
project only opens that notebook inside the same already-running
server rather than starting another one. If a notebook needs a package
beyond caddie's own baseline, that's `/caddie-add-dependency`, not
editing caddie's own `pyproject.toml`.

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

   `status: already-running` means your shared workspace server is
   already up (whether or not it already had this particular notebook
   open) and its URL is being reused; `status: started` means it was
   just launched for the first time (headless, no browser opened by
   marimo itself — this skill opens one below instead). The command
   also prints `file:` — this project's notebook's absolute path,
   needed in the next step since the server may be hosting several
   projects' notebooks at once.

3. Open the printed `url`, with `?file=<file>&view-as=present`
   appended — `<file>` is the exact path `notebook-edit` printed as
   `file:`, URL-encoded (e.g.
   `http://localhost:2718/?file=%2FUsers%2F...%2Fnotebook.py&view-as=present`).
   Both are real marimo query parameters, not a separate server mode:
   it's the same shared edit-mode server, just selecting which
   project's notebook to load (`file`) and landing the browser on
   marimo's "Present" view for it (code hidden, outputs and data
   tables rendered live) instead of the code-visible editor. The user
   can still switch back to the editor from within the page using
   marimo's own view toggle if they want to see or change the code —
   this only picks which notebook and which view loads first. In the
   Claude Code desktop app (Browser pane available), call
   `preview_start` with that full URL directly — no
   `.claude/launch.json` entry is needed or wanted here. `caddie
   notebook-edit` already owns the server's lifecycle (finding an
   existing one vs. starting a new one, on its own port); a
   launch.json config that tries to start its own copy (e.g. a
   hardcoded `--port`) only adds a second, worse way to do the same
   thing, and risks colliding with an unrelated process already on
   that port or going stale and pointing at a notebook that no longer
   exists. Outside the desktop app, run `open "<url with both query
   params>"` (macOS) via a shell command instead — plain CLI chat
   can't render a URL as clickable.

4. Relay to the user:
   - Whether a new server was started or an existing one reused.
   - The URL (with both query params) as plain text as a fallback in
     case opening it failed, and a one-line note that the code-visible
     editor is one click away in the page's own view toggle if they
     want to edit a cell.
   - If the command printed a `note:` line (an existing server that
     wasn't started with `--no-token`), pass that caveat along
     verbatim — the user may need a token from wherever they first
     started it.

## Caveat: never hand-edit `notebook.py` while its server is open

A live marimo server can overwrite its notebook's file on disk with
its own in-memory copy at any time (autosave, browser reconnect). If
you edit that file directly while the server has it open, your edit
can get silently wiped out.
