---
name: caddie-ask
description: The enforced entry point for data analysis with Caddie — never answer a data question with just an inline chat result or a single query. Clarifies the question, states a plan before pulling data, iterates against the active connector until it has a real answer (revising the plan if execution reveals it was wrong), and hands back a rendered, click-to-open notebook. Trigger on "/caddie-ask <question>", and also treat a plain follow-up data question later in the same conversation as an implicit continuation of the active project (see Continuation below).
---

# /caddie-ask "<question>"

`/caddie-ask` never answers a data question inline, and never stops at
one query. It clarifies what's actually being asked, states a plan
before touching data, executes it — revising the plan in place if a
result reveals a wrong assumption — and concludes with a real,
natural-language answer plus a notebook the user can just open.

Notebook-lifecycle mechanics (writing/executing cells, rendering the
final HTML) live in four CLI commands. This skill's job is to drive
the loop: clarify, plan, execute, decide, answer. It does not build
cells or run queries itself — every one of those is a script call.

## Steps

1. Read `~/.caddie/caddie.yaml`. If it doesn't exist, tell the user to
   run `/caddie-install` first and stop here.

2. Determine the target project (see Continuation below). Keep track
   of the active project's slug and episode number for the rest of the
   conversation once you know them — a plain follow-up later reuses
   the project (as a new episode).

3. Invoke the analytics skill named in `caddie.yaml`'s `skills` list
   via the Skill tool, for org-specific grounding — table/column names,
   metric definitions, an example query. Treat its response as input
   to your own plan and queries below, not as a code block to insert
   verbatim.

4. **Clarify** anything genuinely ambiguous before planning: the time
   range, any segment/filter the question implies, the granularity for
   a time series, and — when it isn't obvious — what decision the
   answer needs to support. Ask the user rather than guess (same
   standard as the Continuation judgment call below); skip asking when
   the question is already fully specified.

5. Start the episode:

   ```
   caddie notebook-start --question "<question>" [--project <slug>]
   ```

   Omit `--project` for a new project; the script derives and prints
   the slug. Note the printed `episode` number.

6. Write the plan — the decision being supported, the scope (segments/
   time range/granularity), and the anticipated approach — and record
   it:

   ```
   caddie notebook-plan --project <slug> --episode <N>
   ```
   with the plan text on stdin. `notebook-step` refuses to run until
   this exists.

7. Execute. For each step, author the code yourself (grounded in what
   the analytics skill told you) and run:

   ```
   caddie notebook-step --project <slug> --episode <N> [--kind query|chart] [--label "<why>"]
   ```
   with the code on stdin (default `--kind query`). Read back
   `rows`/`columns`/`preview` (or the chart's figure description).
   After each step, decide:
   - **Continue** — the question isn't answered yet; author the next
     query.
   - **Revise the plan** — a result reveals a wrong assumption (wrong
     table, wrong grain, a segment that doesn't exist); call
     `notebook-plan` again with the updated plan explaining what
     changed and why, then keep executing.
   - **Add a chart** — only when a chart is genuinely the clearest way
     to convey the result (a trend, a comparison across segments, a
     distribution). If the answer is a single number or a short table
     already reads clearly, skip it — a chart nobody needs is clutter,
     not a bonus.
   - **Conclude** — you have enough to answer.

   Cap yourself at 4 total steps (charts count toward the cap). If you
   hit it unresolved, stop and answer with the best available evidence
   plus an explicit caveat rather than continuing indefinitely.

   A note on what the preview can and can't tell you: pushing
   aggregation/filtering into the SQL itself is how this scales to real
   data volumes — the preview is bandwidth for your own reasoning, not
   the mechanism for "seeing more data" (raise `--preview-rows`, capped
   at 500, only when you genuinely need a wider look, e.g. sanity-
   checking a longer breakdown). If answering truly requires judging
   many individual rows rather than a SQL aggregate — categorizing free
   text, eyeballing for anomalies that don't reduce to a `GROUP BY` —
   recognize that and say so plainly in the answer (sample size, an
   honest caveat that it's a sample) rather than implying you saw
   everything.

8. Write the conclusion:

   ```
   caddie notebook-answer --project <slug> --episode <N>
   ```
   with the real natural-language answer on stdin — a number, a short
   table, whatever the question actually needs. This also renders the
   whole notebook to a static HTML file; read back `rendered`/`open`
   from its output.

9. Relay to the user:
   - The answer text itself — a genuine conclusion, not row/column
     counts.
   - The `open` link as a clickable line (e.g.
     `[Open analysis](file:///Users/.../notebook.html)`) — that's what
     the user actually opens; `notebook.py` remains the editable source
     if they want to modify it in `marimo edit` themselves.
   - If the plan was revised mid-analysis, a one-line note that it was
     (the full plan is in the notebook, not repeated in chat).
   - If a step failed and you answered from what remained, say so.
   - Never paste raw preview rows into chat.

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
