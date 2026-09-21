---
name: ask
description: The enforced entry point for data analysis with Caddie — never answer a data question with just an inline chat result or a single query. Clarifies the question, gets a plan from lead-analyst, hands the whole plan to data-analyst to execute front to back in one call against the active connector, gets the final answer back from lead-analyst, and hands back a live, click-to-open notebook (via /caddie:edit) with working data previews, not just a static export. Trigger on /caddie:ask followed by a question, and also treat a plain follow-up data question later in the same conversation as an implicit continuation of the active project (see Continuation below).
---

# /caddie:ask "<question>"

`/caddie:ask` never answers a data question inline, and never stops at
one query. It clarifies what's actually being asked, gets a plan from
the `lead-analyst` sub-agent, hands the whole plan to the
`data-analyst` sub-agent to execute front to back against the active
connector in one call, gets the final answer back from `lead-analyst`,
and hands back a notebook the user can just open.

This skill is the orchestrator: it owns every `caddie` CLI call, every
`marimo-pair` pairing call, and every sub-agent invocation, but it does
not write queries or interpret results itself — see Orchestration
below. Only `notebook-start` (creating the file a kernel would attach
to) and the final HTML render are plain CLI file operations; every
other write to the notebook for the rest of the episode — the plan
cell, every step (inside `data-analyst`), and the answer cell — goes
through the one paired kernel this skill starts right after
`notebook-start`, via the `marimo-pair` skill, the same mechanism
`data-analyst` uses for steps (`agents/data-analyst.md`,
`.specs/requirements-marimo-pair.md`). Query authoring and execution
live in `data-analyst`; planning and interpretation live in
`lead-analyst` (`agents/lead-analyst.md`).

## Spawning rules

These apply to every sub-agent call this skill makes:

- Never invoke `lead-analyst` and `data-analyst` concurrently, and
  never invoke either agent concurrently with itself. Each call must
  fully return before the next one is issued.
- `lead-analyst` is called twice per episode (plan, then interpret).
  `data-analyst` is called exactly once per episode, to run the whole
  plan. Neither agent can be resumed or expected to remember an earlier
  call — treat every call as a fresh spawn and include everything it
  needs directly in its prompt (the plan text verbatim, for
  `data-analyst`; the plan text and `data-analyst`'s report, verbatim,
  for the interpretation call). Don't reference "the plan from earlier"
  — restate it.

## Invoking the CLI

All the caddie CLI commands need to be run using `uv run`.  e.g. `uv run caddie
notebook-start ...`.

## Pairing with the notebook's kernel

A brand-new project's notebook doesn't exist yet, so `caddie
notebook-start` has to create it (step 5 below) before there's anything
to pair with — that's the one raw file write in this whole flow. Every
project that already exists already has a kernel a follow-up can pair
with, so a continuation's `question_{E}` cell is written through
pairing too, exactly like the plan and answer cells — never by calling
`notebook-start` again for an existing project.

Ensure a paired session exists (right after `notebook-start` for a new
project; as the very first thing, before writing anything, for a
continuation):

1. Run `caddie notebook-edit --project <slug>`. This finds or starts
   the user's shared marimo workspace server and, since nothing else
   would otherwise open this notebook in a browser here, opens it
   itself and waits briefly for its session to register. Its output
   gives you `url` (the shared server — also what `data-analyst` will
   reuse) and `file` (this project's notebook's absolute path). If it
   reports `session: none`, pairing could not be established: stop and
   report to the user exactly what failed and why.
2. Invoke the `marimo-pair` skill (via the `Skill` tool) and run its
   required first call before anything else:
   ```
   bash <skill-dir>/scripts/execute-code.sh --url <url> --file <file> \
     -c "import marimo._code_mode as cm; help(cm)"
   ```
   Do this once per episode, before any other `cm` usage.
3. For a **new project only**, the notebook file was just created and its
   `setup` cell (the one defining `mo` and the connector) has never run in
   this kernel — opening the browser tab does not guarantee its autorun has
   finished before you start issuing `cm` calls. Check its status and run it
   if stale, before creating `question_1`/`plan_1`, or a cell referencing
   `mo` can fail with `NameError: name 'mo' is not defined` (see "A
   brand-new notebook's cells may not have run yet" in
   `.claude/skills/marimo-pair/reference/gotchas.md`):
   ```
   bash <skill-dir>/scripts/execute-code.sh --url <url> --file <file> \
     -c "import marimo._code_mode as cm; print(cm.get_context().cells['setup'].status)"
   ```
   If it prints `stale`, run it (as its own `execute-code.sh` call, inside
   `async with cm.get_context() as ctx: ctx.run_cell('setup')`) before
   continuing. Skip this for a continuation — an existing project's kernel
   has already run `setup`.

Every cell this orchestrator writes goes through that paired session —
a scratchpad `execute-code.sh` call running Python inside `async with
cm.get_context() as ctx:`, per whatever exact call shape `help(cm)`
showed you. Use these shapes:

- **Question cell** (continuation only): name `question_{E}`, code
  `mo.md({question_markdown!r})`, created at the end of the notebook
  (after the prior episode's `answer_{E-1}`).
- **Plan cell**: name `plan_{E}`, code `mo.md({plan_markdown!r})` (a
  Python `repr()` of the markdown text, not a triple-quoted template).
  Create it immediately after `question_{E}`. If it already exists (a
  mid-episode revision), edit that cell in place instead — read its
  current body first, per marimo pair's own guidance.
- **Answer cell**: name `answer_{E}`, code
  `mo.md({answer_markdown!r})`, created once at the end (never edited —
  one answer per episode; if you find yourself about to write a second
  one, something upstream is wrong, not something to paper over here).

Build the `repr()` inline, in the same Python that's fed to
`execute-code.sh`, in a single call — don't round-trip the markdown
through bash first (e.g. `cat`-ing it to a file, `exec`-ing it to
compute a `repr()`, then re-injecting that into a second script). A
quoted heredoc (`<<'PYEOF'`) passes the markdown through bash
unmodified, so a triple-quoted variable *inside that scratchpad script*
is fine — it's never the notebook's saved cell code, only the
single-line `f"mo.md({{...!r}})"` result is:

```bash
bash <skill-dir>/scripts/execute-code.sh --url <url> --file <file> - <<'PYEOF'
import marimo._code_mode as cm

PLAN_MD = """## Analysis Plan
...actual markdown, verbatim...
"""

async with cm.get_context() as ctx:
    cid = ctx.create_cell(f"mo.md({PLAN_MD!r})", name="plan_1")
    ctx.run_cell(cid)
PYEOF
```

The same one-call pattern applies to `question_{E}` and `answer_{E}`.

`data-analyst` pairs with this same server for its own step cells
(`description_{E}_{S}`/`code_{E}_{S}`/`chart_{E}_{S}`/`output_{E}_{S}`)
— see its own agent file for that shape. This orchestrator never writes
a step cell itself.

## Orchestration

1. Read `~/.caddie/caddie.yaml`. If it doesn't exist, tell the user to
   run `/caddie:install` first and stop here.

2. Determine the target project (see Continuation below). Keep track
   of the active project's slug and episode number for the rest of the
   conversation once you know them — a plain follow-up later reuses
   the project (as a new episode).

3. **Clarify** anything genuinely ambiguous before planning: the time
   range, any segment/filter the question implies, the granularity for
   a time series, and — when it isn't obvious — what decision the
   answer needs to support. Do this yourself, directly with the user,
   in a plain conversational exchange — not a sub-agent call. Skip
   asking when the question is already fully specified (same judgment
   call as Continuation below).

4. **Call `lead-analyst` (planning call)** via the `Agent` tool, with
   the clarified question and, if this is a continuation, a pointer
   (file path, via `Read`) to prior episode/notebook context. It
   returns the plan: an ordered list of steps, each with a description,
   what it establishes, and a contingency.

5. Start the episode, pair, and record the plan. This branches on
   whether step 2 found a new project or a continuation:

   a. **New project**: run
      ```
      caddie notebook-start --question "<question>"
      ```
      to create it — the script derives and prints the slug. Then
      ensure a paired kernel session exists: follow "Pairing with the
      notebook's kernel" above (`caddie notebook-edit --project <slug>`
      finds or starts the shared server and its session for this
      notebook automatically; then the required `marimo-pair` first
      call). Note the printed `episode` number (always `1` here).

   b. **Continuation**: ensure a paired kernel session exists first
      (same "Pairing with the notebook's kernel" sequence, against the
      existing `--project <slug>`), then write the new `question_{E}`
      cell through it, per the shape given above. Determine `E` as one
      more than the highest `question_{E}` already in the notebook.

   In either case, if pairing reports `session: none`, pairing could
   not be established: stop and report to the user exactly what failed
   and why.

   c. Write the `plan_{E}` cell through that paired session
      (`lead-analyst`'s plan text verbatim), per the shape given above.

6. **Call `data-analyst`** via the `Agent` tool, with the full plan
   text (verbatim, including contingencies), the project slug, and the
   episode number. It pairs with the same live kernel this skill
   already started (`caddie notebook-edit` reuses it) and works through
   the entire plan front to back in this one call, applying
   contingencies as needed, and returns a consolidated report plus a
   plain status: plan fully executed, or stopped at an uncovered
   deviation. Relay a one-line note per step to the user as the report
   comes back (what the step was, whether it succeeded or a contingency
   was applied), and a note if a contingency was applied at all. Never
   relay raw preview rows.

7. **Call `lead-analyst` again (interpretation call)** via the `Agent`
   tool — this is a second, independent invocation; the planning call
   has already returned, so this doesn't violate "never concurrently
   with itself." Since every call is stateless, include the plan text
   from step 4 and `data-analyst`'s full report from step 6, verbatim,
   in this call's prompt — don't reference either by assumption. It
   returns the final natural-language answer, with a caveat baked in if
   `data-analyst` hit an uncovered deviation.

8. Write the conclusion through the same paired kernel from step 5 —
   `lead-analyst`'s answer text (verbatim), as the `answer_{E}` cell
   per "Pairing with the notebook's kernel" above. Once the cell is
   written, confirm it actually landed on disk before moving on (the
   paired kernel autosaves, but don't assume instantaneous — a quick
   check that `answer_{E}` is in the file is cheap insurance), then
   render the static HTML separately:
   ```
   caddie notebook-render --project <slug>
   ```
   Read back `rendered`/`open` from its output. Keep that path as a
   fallback for step 10 — the real thing to open next is the live
   notebook, not this static export.

9. Open the notebook live rather than the static export: invoke the
   `edit` skill (/caddie:edit) for this project (same as a user typing
   `/caddie:edit <slug>` themselves) — it finds the same shared server
   this episode has already been pairing against and opens it landed on
   marimo's "Present" view (`?file=<file>&view-as=present`). This
   matters, not just style: the static HTML from step 8 has no running
   kernel, so any `mo.ui.table`/dataframe output in it degrades to an
   inert "Preview data" button that can't fetch rows — the live server
   actually renders the data. Do this every time, not just on request.
   Since every write this episode already went through that same live
   kernel (not a direct file edit), there's no stale-clobber risk here
   the way there would be after a raw file write — this step is just
   making sure the user is looking at the right view of a session
   that's already correct.

10. Relay to the user:
    - The answer text itself, exactly as `lead-analyst` returned it —
      a genuine conclusion, not row/column counts. It should directly
      address the question that was asked and support the decision
      being made.
    - A one-line note that the notebook opened live in their browser
      (via `/caddie:edit`), plus its URL as plain text as a fallback in
      case the open failed. Mention the static rendered path from step
      8 only as a secondary fallback (e.g. if the live server couldn't
      start) — it's not the primary artifact anymore, since it can't
      show live data.
    - If a contingency was applied mid-run, or `data-analyst` stopped
      at an uncovered deviation, a one-line note that it happened (the
      full detail is in the notebook, not repeated in chat).
    - Never paste raw preview rows into chat.

A plan that turns out wrong in a way `data-analyst` wasn't authorized
to work around isn't something this flow loops back to fix mid-episode
— it ends with a caveat from `lead-analyst`'s interpretation call
instead. A genuine do-over is a new episode: a follow-up question
already starts a new episode under Caddie's existing continuation model
(see Continuation below).

## Continuation

A follow-up data question later in the same conversation is an
implicit continuation of the active project — it is never answered as
plain chat, and the user never needs to retype `/caddie:ask`. A
continuation starts a *new episode* in the same project (step 5b: pair
with that project's kernel, then write the new `question_{E}` cell
through it), not a new step in the old episode — steps belong to one
line of inquiry within a single `/caddie:ask` turn.
Judging whether something is a continuation at all is a judgment call,
not a fixed trigger:

- A clarifying question about the existing notebook, or a follow-up
  that reshapes the question but is clearly part of the same analysis
  → continuation.
- A clearly unrelated new topic → new project; omit `--project`.
- Genuinely ambiguous → ask the user which one they mean rather than
  guessing.
