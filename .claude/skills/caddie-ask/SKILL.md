---
name: caddie-ask
description: The enforced entry point for data analysis with Caddie — never answer a data question with just an inline chat result. Invokes the org's configured analytics skill for the question, builds and executes a Marimo notebook cell group against the active data connector, and reports the notebook path plus a compact summary in chat. Trigger on "/caddie-ask <question>", and also treat a plain follow-up data question later in the same conversation as an implicit continuation of the active project (see Continuation below).
---

# /caddie-ask "<question>"

`/caddie-ask` never answers a data question inline. It always produces
or extends a Marimo notebook, running the actual query through the
active connector, before reporting back.

Notebook-lifecycle mechanics — building or appending the cell group,
executing it, and computing the summary — live in `caddie
notebook-build`. This skill's job is to pick the right analytics skill
for the question and relay that script's output; it does not build
cells, run queries, or compute summaries itself.

## Steps

1. Read `~/.caddie/caddie.yaml`. If it doesn't exist, tell the user to
   run `/caddie-install` first and stop here.

2. Determine the target project (see Continuation below). Keep track
   of the active project's slug for the rest of the conversation once
   you know it — a plain follow-up later reuses it.

3. Invoke the analytics skill for this question via the Skill tool,
   using the name(s) from `caddie.yaml`'s `skills` list. If more than
   one is configured, let ordinary Claude Code skill selection (each
   skill's own description/trigger) decide which one fires — Caddie
   does not rank or choose between them itself. Pass it the question
   and the active connector's session/handle. The invoked skill
   produces markdown restating the question plus one fenced code block
   (SQL, or Python against the connector's session) — that is the one
   output shape Caddie cares about.

4. Pipe that raw output into:

   ```
   caddie notebook-build --question "<question>" [--project <slug>]
   ```

   Omit `--project` to start a new project (the script derives and
   prints the slug); pass it to append to the active one. This single
   call builds or appends the cell group *and* executes it against the
   connector the project was created with, so the notebook's output
   cell reflects real results the next time it's opened in `marimo
   edit`.

5. Relay the result to the user — never reformat away the distinction
   between success and failure:
   - `status: ok` — report the notebook's absolute file path and a
     short summary built from the printed `rows`/`columns` lines.
     Never paste the full raw row-level output into chat.
   - `status: error` — the cell group was still written to the
     notebook, but tell the user plainly that the query failed and
     show the printed `error` line. Do not claim success.

## Continuation

A follow-up data question later in the same conversation is an
implicit continuation of the active project — it is never answered as
plain chat, and the user never needs to retype `/caddie-ask`. Judging
this is a judgment call, not a fixed trigger:

- A clarifying question about the existing notebook, or a follow-up
  that reshapes the question but is clearly part of the same analysis
  → continuation; pass `--project <active-slug>`.
- A clearly unrelated new topic → new project; omit `--project`.
- Genuinely ambiguous → ask the user which one they mean rather than
  guessing.
