---
name: caddie-ask
description: The enforced entry point for data analysis with Caddie — never answer a data question with just an inline chat result or a single query. Clarifies the question, gets a plan from lead-analyst, hands execution to data-analyst in batches against the active connector (checking with the user before each further batch), gets the final answer back from lead-analyst, and hands back a live, click-to-open notebook (via caddie-edit) with working data previews, not just a static export. Trigger on "/caddie-ask <question>", and also treat a plain follow-up data question later in the same conversation as an implicit continuation of the active project (see Continuation below).
---

# /caddie-ask "<question>"

`/caddie-ask` never answers a data question inline, and never stops at
one query. It clarifies what's actually being asked, gets a plan from
the `lead-analyst` sub-agent, hands the plan to the `data-analyst`
sub-agent to execute against the active connector in batches of up to 4
steps — checking with the user before running a further batch — gets
the final answer back from `lead-analyst`, and hands back a notebook
the user can just open.

This skill is the orchestrator: it owns every `caddie` CLI call and
every sub-agent invocation, but it does not write queries or
interpret results itself — see Orchestration below. Notebook-lifecycle
mechanics (writing/executing cells, rendering the final HTML) live in
four CLI commands; query authoring and execution live in
`data-analyst` (`.claude/agents/data-analyst.md`); planning and
interpretation live in `lead-analyst` (`.claude/agents/lead-analyst.md`).

## Spawning rules

These apply to every sub-agent call this skill makes:

- Never invoke `lead-analyst` and `data-analyst` concurrently, and
  never invoke either agent concurrently with itself. Each call must
  fully return before the next one is issued.
- `lead-analyst` is called twice per episode (plan, then interpret).
  `data-analyst` is called once per batch of up to 4 steps — once at
  minimum, and again for each further batch the user approves (see
  Orchestration step 6). Neither agent can be resumed or expected to
  remember an earlier call — treat every call as a fresh spawn and
  include everything it needs directly in its prompt (the plan text
  verbatim, the batch size, and — for a second-or-later `data-analyst`
  batch — which steps already ran plus the consolidated report(s) so
  far, verbatim). Don't reference "the plan from earlier" or "the
  report from the last batch" — restate it.

## Invoking the CLI

All the caddie CLI commands need to be run using `uv run`.  e.g. `uv run caddie
notebook-start ...`.

## Orchestration

1. Read `~/.caddie/caddie.yaml`. If it doesn't exist, tell the user to
   run `/caddie-install` first and stop here.

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

5. Start the episode and record the plan:

   ```
   caddie notebook-start --question "<question>" [--project <slug>]
   ```
   Omit `--project` for a new project; the script derives and prints
   the slug. Note the printed `episode` number. Then:
   ```
   caddie notebook-plan --project <slug> --episode <N>
   ```
   with `lead-analyst`'s plan text (verbatim) on stdin.

6. **Run `data-analyst` in batches of up to 4 steps**, checking with the
   user before each batch after the first:

   a. **Call `data-analyst`** via the `Agent` tool, with the full plan
      text (verbatim, including contingencies), the project slug, the
      episode number, the batch size (4), and — for any call after the
      first — which steps already ran and the consolidated report(s)
      from earlier batches, verbatim, so it knows where to pick up. It
      authors and runs up to 4 steps via `caddie notebook-step`,
      applying contingencies as needed, and returns a consolidated
      report for this batch plus a plain status: plan fully executed,
      steps remain, or stopped at an uncovered deviation.

   b. Relay a one-line note per step to the user as the report comes
      back (what the step was, whether it succeeded or a contingency
      was applied), and a note if a contingency was applied at all.
      Never relay raw preview rows.

   c. If the plan is fully executed, or `data-analyst` stopped at an
      uncovered deviation, move on to step 7 — there's nothing left to
      ask permission for.

   d. If steps remain and nothing stopped it, ask the user whether to
      run another batch (e.g. via `AskUserQuestion`) rather than
      continuing on your own — this permission check, every batch
      after the first, replaces what used to be a hard step cap. If
      they say yes, repeat from (a) for the next batch. If they say no,
      move on to step 7 with whatever's been run so far; the answer
      will need a caveat that the analysis stopped early by choice, not
      because it was finished or blocked.

7. **Call `lead-analyst` again (interpretation call)** via the `Agent`
   tool — this is a second, independent invocation; the planning call
   has already returned, so this doesn't violate "never concurrently
   with itself." Since every call is stateless, include the plan text
   from step 4 and `data-analyst`'s full consolidated report — every
   batch from step 6, concatenated — verbatim in this call's prompt —
   don't reference either by assumption. It returns the final
   natural-language answer, with a caveat baked in if `data-analyst`
   hit an uncovered deviation or the user chose not to run a further
   batch before the plan was done.

8. Write the conclusion:

   ```
   caddie notebook-answer --project <slug> --episode <N>
   ```
   with `lead-analyst`'s answer text (verbatim) on stdin. This also
   renders the whole notebook to a static HTML file; read back
   `rendered`/`open` from its output. Keep that path as a fallback for
   step 10 — the real thing to open next is the live notebook, not this
   static export.

9. Open the notebook live rather than the static export: invoke the
   `caddie-edit` skill for this project (same as a user typing
   `/caddie-edit <slug>` themselves) — it finds or starts a marimo edit
   server for the notebook and opens it landed on marimo's "Present"
   view (`?view-as=present`). This matters, not just style: the static
   HTML from step 8 has no running kernel, so any `mo.ui.table`/
   dataframe output in it degrades to an inert "Preview data" button
   that can't fetch rows — the live server actually renders the data.
   Do this every time, not just on request. Do it only now, after every
   `caddie notebook-step`/`notebook-answer` write for this episode is
   done — `caddie-edit`'s own caveat about a stale already-running
   server clobbering on-disk edits applies here too: if a server for
   this project was already open from earlier in the session, this step
   reconnects it to what's now on disk rather than racing it.

10. Relay to the user:
    - The answer text itself, exactly as `lead-analyst` returned it —
      a genuine conclusion, not row/column counts. It should directly
      address the question that was asked and support the decision
      being made.
    - A one-line note that the notebook opened live in their browser
      (via `caddie-edit`), plus its URL as plain text as a fallback in
      case the open failed. Mention the static rendered path from step
      8 only as a secondary fallback (e.g. if the live server couldn't
      start) — it's not the primary artifact anymore, since it can't
      show live data.
    - If a contingency was applied mid-run, `data-analyst` stopped at
      an uncovered deviation, or the user chose not to run a further
      batch, a one-line note that it happened (the full detail is in
      the notebook, not repeated in chat).
    - Never paste raw preview rows into chat.

A plan that turns out wrong in a way `data-analyst` wasn't authorized
to work around isn't something this flow loops back to fix mid-episode
— it ends with a caveat from `lead-analyst`'s interpretation call
instead, same as when the user declines a further batch. A genuine
do-over is a new episode: a follow-up question already starts a new
episode under Caddie's existing continuation model (see Continuation
below).

## Continuation

A follow-up data question later in the same conversation is an
implicit continuation of the active project — it is never answered as
plain chat, and the user never needs to retype `/caddie-ask`. A
continuation starts a *new episode* in the same project (step 5, with
`--project <active-slug>`), not a new step in the old episode — steps
belong to one line of inquiry within a single `/caddie-ask` turn.
Judging whether something is a continuation at all is a judgment call,
not a fixed trigger:

- A clarifying question about the existing notebook, or a follow-up
  that reshapes the question but is clearly part of the same analysis
  → continuation.
- A clearly unrelated new topic → new project; omit `--project`.
- Genuinely ambiguous → ask the user which one they mean rather than
  guessing.
