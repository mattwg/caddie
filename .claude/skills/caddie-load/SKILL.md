---
name: caddie-load
description: Bring an existing Caddie analysis project back into context in any conversation, including one that never ran /caddie-ask for it — loads its episodes (question, plan, steps, answer), re-executes every step by default against the connector it was created with, reports what changed since the last run, and re-renders a click-to-open notebook. Trigger on "/caddie-load <project>".
---

# /caddie-load <project>

Re-establishes an existing project as the active analysis, so a plain
follow-up question afterward behaves exactly like an implicit
`/caddie-ask` continuation (see that skill's Continuation section) —
the user never needs to retype `/caddie-ask` after loading.

Re-executing every episode's steps and comparing row counts to the
previous run lives in `caddie notebook-rerun`. This skill's job is to
load the notebook's contents into the conversation and relay that
script's output; it does not re-run queries or diff results itself.

## Invoking the CLI

The command below assumes `caddie` is on `PATH`. If the working
directory is a checkout of the Caddie project itself (look for a
`pyproject.toml` with `name = "caddie"` at or above the working
directory), the `caddie` entry point only exists inside that project's
own virtualenv — running it bare will fail with `command not found`.
In that case, prefix it with `uv run`, e.g. `uv run caddie
notebook-rerun ...`. Check for this once at the start rather than
discovering it after a failed call.

## Steps

1. Read the notebook file directly (`~/caddie/notebooks/<username>/
   <project>/notebook.py`, or the configured `notebooks_root` if
   overridden) so its episodes — question, plan, steps, answer — are
   in context. If it doesn't exist, tell the user and suggest
   `/caddie-list` to find the right slug.

2. Run:

   ```
   caddie notebook-rerun --project <project>
   ```

   This re-executes every step (query and chart) in every episode, in
   order, against the connector recorded for that project — not
   necessarily the connector currently active in `caddie.yaml` — and
   updates its recorded stats for next time. It also re-renders the
   notebook to a static HTML file. The notebook's own cells are never
   rewritten by this step.

3. Open the rendered notebook for the user: run `open <rendered path>`
   (macOS) via a shell command — Claude Code's chat UI can't render a
   `file://...` link as clickable, so launching it directly is the
   only way a click isn't required. Do this every time, not just on
   request.

4. Relay the result:
   - Report a concrete comparison to the previous run for each query
     step that succeeded (the row-count delta the script prints), not
     just "it ran"; for a chart step, report whether it still produces
     a valid figure.
   - Note each episode's current plan and answer (printed as
     `episode {N} plan:` / `episode {N} answer:`) so the user has the
     substance, not just the execution status.
   - If a specific step now fails (e.g. a dropped or renamed column),
     still tell the user the project loaded successfully — they can
     see and discuss the notebook regardless — but call out that
     step's re-run error clearly and specifically, quoting the printed
     error rather than summarizing it away.
   - A one-line note that the notebook opened in their browser, plus
     the absolute path as plain text as a fallback in case the open
     command failed (e.g. no default browser handler) — not formatted
     as a `file://` link.
   - `overall: ok` — everything re-ran cleanly.
   - `overall: partial` — some steps (or the render itself) failed;
     list which ones.

5. Treat this project as the active one for the rest of the
   conversation: a plain follow-up afterward is an implicit
   continuation, same as with `/caddie-ask` — a new episode in this
   project (`caddie notebook-start --project <this project>`), not a
   new step in an old one.
