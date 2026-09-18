---
name: caddie-load
description: Bring an existing Caddie analysis project back into context in any conversation, including one that never ran /caddie-ask for it — loads its cells, re-executes the whole notebook by default against the connector it was created with, and reports what changed since the last run. Trigger on "/caddie-load <project>".
---

# /caddie-load <project>

Re-establishes an existing project as the active analysis, so a plain
follow-up question afterward behaves exactly like an implicit
`/caddie-ask` continuation (see that skill's Continuation section) —
the user never needs to retype `/caddie-ask` after loading.

Re-executing every cell group and comparing row counts to the previous
run lives in `caddie notebook-rerun`. This skill's job is to load the
notebook's contents into the conversation and relay that script's
output; it does not re-run queries or diff results itself.

## Steps

1. Read the notebook file directly (`~/caddie/notebooks/<username>/
   <project>/notebook.py`, or the configured `notebooks_root` if
   overridden) so its questions, code, and prior structure are in
   context. If it doesn't exist, tell the user and suggest
   `/caddie-list` to find the right slug.

2. Run:

   ```
   caddie notebook-rerun --project <project>
   ```

   This re-executes every cell group, in order, against the connector
   recorded for that project — not necessarily the connector currently
   active in `caddie.yaml` — and updates its recorded row counts/
   columns for next time. The notebook file itself is never rewritten
   by this step.

3. Relay the result:
   - Report a concrete comparison to the previous run for each group
     that succeeded (e.g. the row-count delta the script prints), not
     just "it ran."
   - If a specific group's query now fails (e.g. a dropped or renamed
     column), still tell the user the project loaded successfully —
     they can see and discuss the notebook regardless — but call out
     that group's re-run error clearly and specifically, quoting the
     printed error rather than summarizing it away.
   - `overall: ok` — everything re-ran cleanly.
   - `overall: partial` — some groups failed; list which ones.

4. Treat this project as the active one for the rest of the
   conversation: a plain follow-up afterward is an implicit
   continuation, same as with `/caddie-ask` (pass `--project <this
   project>` to `caddie notebook-build` when it happens).
