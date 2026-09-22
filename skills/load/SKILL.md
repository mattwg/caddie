---
name: load
description: Bring an existing Caddie analysis project back into context in any conversation, including one that never ran /caddie:ask for it — loads its episodes (question, plan, steps, answer), re-executes every step live against the project's kernel so the notebook's stored results are genuinely current, and hands back a live, click-to-open notebook. Trigger on /caddie:load followed by a project name.
---

# /caddie:load <project>

Re-establishes an existing project as the active analysis, so a plain
follow-up question afterward behaves exactly like an implicit
`/caddie:ask` continuation (see that skill's Continuation section) —
the user never needs to retype `/caddie:ask` after loading.

Re-execution pairs with the project's live kernel (via the
`marimo-pair` skill), the same mechanism `/caddie:ask` and
`data-analyst` use, so a reloaded notebook shows genuinely current
results rather than a stale snapshot.

## Invoking the CLI

The command below assumes `caddie` is already on `PATH` (installed
separately from this plugin, e.g. via `uv tool install caddie`). If it
fails with `command not found`, point the user at `/caddie:install`
rather than guessing at a workaround.

## Steps

1. Read the notebook file directly (`~/caddie/notebooks/<project>/
   notebook.py`, or the configured `notebooks_root` if overridden) so
   its episodes — question, plan, steps, answer — are in context. If
   it doesn't exist, tell the user and suggest `/caddie:list` to find
   the right slug.

2. Pair with the project's kernel:

   a. Run `caddie notebook-edit --project <project>`. It gives you
      `url` and `file` (this project's notebook's absolute path).
   b. Invoke the `marimo-pair` skill (via the `Skill` tool) and run its
      required first call:
      ```
      bash <skill-dir>/scripts/execute-code.sh --url <url> --file <file> \
        -c "import marimo._code_mode as cm; help(cm)"
      ```

   If step 2a reports `session: none`, pairing failed — skip to step 6
   and relay the notebook's contents read-only (from step 1), with a
   note that nothing was re-run.

3. Re-run every existing step, in order, across every episode: find
   each `code_{E}_{S}`/`chart_{E}_{S}` cell (via `ctx.cells`, per
   whatever exact shape `help(cm)` showed) and re-run it with `cm`'s
   run-cell operation. For each one, check its resulting status/errors,
   and read back a query's row count or confirm a chart still produces
   a valid figure via a scratchpad call. This runs against the
   connector the notebook's own `setup` cell configured (its recorded
   connector), not necessarily whatever's active in `caddie.yaml`.

4. Render the static export too: `caddie notebook-render --project
   <project>`. Keep its path as a fallback for step 5.

5. Open the notebook live: invoke the `edit` skill (/caddie:edit) for this
   project. This matters, not just style — only the live server shows
   the freshly re-run results from step 3 with working
   `mo.ui.table`/dataframe previews; the static export is inert.

6. Relay the result:
   - Each query step's outcome (rows returned) and each chart step's
     validity — not just "it ran."
   - Each episode's plan and answer text (from step 1).
   - Any step that now fails (e.g. a dropped column): say the project
     still loaded fine, but quote that step's actual error.
   - The live URL, with the static path as a fallback if opening it
     failed.
   - `overall: ok` or `overall: partial` (list what failed).
   - If pairing failed (step 2), say so plainly and that nothing was
     re-run.

7. Treat this project as the active one for the rest of the
   conversation — a plain follow-up afterward is an implicit
   continuation, same as `/caddie:ask`'s own Continuation behavior: a
   new episode in this project (pair with its kernel, already
   established above, and write the new `question_{E}` cell through
   it), not a new step in an old one.
