---
name: explore
description: >-
  Build a Caddie analysis notebook step by step, under direct user
  direction, rather than solving a question autonomously — "add a cell
  that computes metric X by these groups," "now break that down by
  country," "add a chart for that," "clean up the cells I don't need
  anymore." Pairs with the project's live marimo kernel directly (via
  marimo-pair) to author, run, revise, or remove each requested cell,
  consulting the org's analytics skill for schema/column grounding
  before writing a query. Trigger on /caddie:explore, and also treat a
  plain follow-up build/cleanup instruction later in the same
  conversation as an implicit continuation of the active explore
  session (see Continuation below).
---

# /caddie:explore ["<project>"] "<instruction>"

`/caddie:ask` is autonomous: it clarifies a question, hands a whole
plan to `lead-analyst`/`data-analyst`, and comes back with a finished
answer. `/caddie:explore` is the opposite mode — the user already
knows what they want built and directs it one instruction at a time:
add a cell, revise a cell, chart something, clean up what's no longer
needed. There's no plan to hand off and no single question being
answered, so this skill never spawns `lead-analyst` or `data-analyst`.
It owns every `caddie` CLI call, every `marimo-pair` pairing call, and
every notebook write itself, the same way `/caddie:ask` owns its own
orchestration — but each instruction is its own small, immediate unit
of work rather than a step in someone else's plan.

Every write to the notebook goes through the one paired kernel this
skill starts at the beginning of the session, via the `marimo-pair`
skill — never a direct file edit while that session is open (see
Caveat at the end).

## Invoking the CLI

Every `caddie ...` command below assumes `caddie` is already on
`PATH` (installed separately from this plugin, e.g. via `uv tool
install caddie`). If a command fails with `command not found`, point
the user at `/caddie:install` rather than guessing at a workaround.

## Pairing with the notebook's kernel

1. **New project**: run
   ```
   caddie notebook-start --question "<first instruction, as a description of what's being explored>"
   ```
   to create it — the script derives and prints the slug. Then
   ensure a paired kernel session exists (step 2 below).

   **Existing project / continuation**: ensure a paired kernel session
   exists first (step 2 below) against `--project <slug>` — the
   project the user named, or the active session from earlier in this
   conversation.

2. Run `caddie notebook-edit --project <slug>`. This finds or starts
   the user's shared marimo workspace server and, since nothing else
   would otherwise open this notebook in a browser here, opens it
   itself and waits briefly for its session to register. Its output
   gives you `url` (the shared server) and `file` (this project's
   notebook's absolute path). If it reports `session: none`, pairing
   could not be established: stop and report to the user exactly what
   failed and why.

3. Invoke the `marimo-pair` skill (via the `Skill` tool) and run its
   required first call before anything else, once per session:
   ```
   bash <skill-dir>/scripts/execute-code.sh --url <url> --file <file> \
     -c "import marimo._code_mode as cm; help(cm)"
   ```

4. For a **new project only**, the notebook's `setup` cell (defining
   `mo` and the connector) has never run in this kernel — opening the
   browser tab does not guarantee its autorun has finished. Check its
   status and run it if stale, before writing any other cell, or a
   cell referencing `mo` can fail with `NameError: name 'mo' is not
   defined` (see "A brand-new notebook's cells may not have run yet"
   in `.claude/skills/marimo-pair/reference/gotchas.md`):
   ```
   bash <skill-dir>/scripts/execute-code.sh --url <url> --file <file> \
     -c "import marimo._code_mode as cm; print(cm.get_context().cells['setup'].status)"
   ```
   If it prints `stale`, run it (inside `async with cm.get_context()
   as ctx: ctx.run_cell('setup')`) before continuing. Skip this for an
   existing project — its kernel has already run `setup`.

5. Open the live view once, right after pairing succeeds — invoke the
   `edit` skill (`/caddie:edit`) for this project, same as a user
   typing `/caddie:edit <slug>` themselves. Do this only the first
   time a session starts, not on every subsequent instruction — this
   is a standing session, not a one-shot turn like `/caddie:ask`.

## Cell shapes

Every durable cell change goes through the paired session — a
scratchpad `execute-code.sh` call running Python inside `async with
cm.get_context() as ctx:`, per whatever exact call shape `help(cm)`
showed. Two kinds of execution: a **scratchpad call** (plain Python
against a copy of kernel state, nothing persists — use this to check
something, e.g. does a column exist, before deciding what to write)
and a **durable cell change** (a real, persisted notebook cell).

Cell naming is a single incrementing step number per notebook, no
episode concept — `N` is one more than the current highest
`code_{N}`/`chart_{N}` already in the notebook (0 if none yet), and
just keeps climbing across the whole session, including across a
project `/caddie:ask` built (mixing autonomous episodes and manual
steps in one notebook is expected).

For a **new step** the user asks for:

- Add a `description_{N}` markdown cell right before the code/chart
  when it adds real value (what the step does, any non-obvious
  filter/segment) — skip it for a trivial one-line tweak.
- `code_{N}` (a query, bound to `query_{N}`/`result_{N}`) or
  `chart_{N}`, then `output_{N}` holding the result/figure — unless
  the instruction is simple enough that folding the display into the
  same cell is clearly simpler; judgment call, not a fixed rule.
- `code_{N}`/`chart_{N}` must only compute and assign — never end on
  a bare `result_{N}`/`chart_{N}` reference when there's a separate
  `output_{N}` cell. Marimo auto-displays a trailing bare expression,
  so ending on one renders the result once there and again in
  `output_{N}` — the same object shown twice for no reason.
- Ground a new query against the org's analytics skill (invoke it via
  the `Skill` tool, same as `data-analyst` does per step) before
  writing it — schema/column precision matters here the same way.

For a **revision** to an existing cell ("change that groupby to
weekly," "fix the filter," "use a bar chart instead") — read the
cell's current body first (per `marimo-pair`'s own guidance, since
another editor could have touched it since), then edit it in place
and re-run it. Don't append a new numbered step for something that's
correcting, not adding to, the analysis.

If a query or chart comes back surprising — an error, or a result
that doesn't match what the user described — say so plainly and ask
how they want to proceed. There's no plan contingency to fall back on
here the way `data-analyst` has; the user's next instruction *is* the
plan.

## Cleanup and refactor instructions

"Remove the cells I don't need anymore," "combine those last three
now that we know X," "drop the orphaned ones," "simplify this" are a
distinct instruction type, not cell-adding — treat one as its own
loop iteration alongside "add a cell" and "revise a cell." This
follows `marimo-pair`'s own
`reference/notebook-improvements.md`, which already covers this
ground — nothing new to invent here:

- **Find candidates** by walking `ctx.graph` — a cell whose
  `descendants` are empty and whose output nothing downstream actually
  references is an orphan candidate. Check with the user before
  deleting anything whose removal isn't obviously safe — marimo
  deletes are destructive, and a cell that looks unused might not be.
- **Consolidating/simplifying** — merging near-duplicate query cells,
  hoisting scattered imports into `setup`, lifting a reusable function
  into its own cell — follows the same guidance in
  `notebook-improvements.md`, applied via `ctx.edit_cell`/deletion on
  the existing cells rather than by adding new numbered steps.
- **Don't renumber survivors.** Gaps in `N` after a cleanup are
  harmless (same convention `data-analyst` follows) — leave surviving
  cells' names as they are rather than renumbering the whole notebook.
- Summarize what was removed or merged, and why, in chat. Never
  silently drop a cell that only looked unused — when genuinely
  unsure, ask rather than delete.

## Loop

For each user instruction, one at a time:

1. Ensure the paired session still exists (it should, for the rest of
   the conversation once established — re-verify only if something
   suggests it dropped).
2. Classify the instruction: new step, revision, or cleanup/refactor
   (see sections above), and act on it through the paired kernel.
3. Confirm in chat what was added, changed, or removed — a one-line
   description and, if useful, the row/column shape of a result.
   Never paste raw preview rows. Do not reopen `/caddie:edit` after
   every instruction — it's already open from pairing.

There's nothing to "finish": no answer cell, no final interpretation
step the way `/caddie:ask` has. The session just ends when the user
stops giving instructions, and the notebook is left exactly as built
or cleaned up.

## Continuation

A plain follow-up build or cleanup instruction later in the same
conversation ("now add a cell for...", "actually combine those two")
is an implicit continuation of the active explore session — the user
never needs to retype `/caddie:explore`. Same judgment call as
`/caddie:ask`'s continuation model:

- Clearly part of the same notebook/session → continuation.
- A clearly unrelated new topic → new project; omit `--project`.
- Genuinely ambiguous → ask the user which project they mean rather
  than guessing.

## Caveat: never hand-edit `notebook.py` while its server is open

A live marimo server can overwrite its notebook's file on disk with
its own in-memory copy at any time (autosave, browser reconnect). If
you edit that file directly (`Edit`/`Write`/`NotebookEdit`) while the
server has it open, your edit can get silently wiped out — always go
through the paired kernel's `cm` API instead.
