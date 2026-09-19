---
name: caddie-edit
description: Open an existing Caddie analysis project in a live marimo edit server — reuses an already-running server for that notebook instead of starting a duplicate, and opens the resulting URL in the browser. Trigger on "/caddie-edit <project>", or when a user asks to edit, tweak, or interact with a notebook that /caddie-ask or /caddie-load already produced (the rendered HTML those hand back is static).
---

# /caddie-edit <project>

`/caddie-ask` and `/caddie-load` hand back a rendered, static HTML
export by default — enough to read the answer, not to rerun a cell or
tweak a query by hand. This skill opens the project's live marimo
editor instead: checking for and running the server itself lives in
`caddie notebook-edit`, which either finds an already-running server
for that exact notebook or starts a new one; this skill's job is to
invoke it and open the URL it prints.

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

3. Open the printed `url` for the user: run `open <url>` (macOS) via a
   shell command — Claude Code's chat UI can't render a plain URL as
   clickable the way a real browser link would auto-launch, so this is
   the only way a click isn't required.

4. Relay to the user:
   - Whether a new server was started or an existing one reused.
   - The URL as plain text as a fallback in case `open` failed.
   - If the command printed a `note:` line (an existing server that
     wasn't started with `--no-token`), pass that caveat along
     verbatim — the user may need a token from wherever they first
     started it.
