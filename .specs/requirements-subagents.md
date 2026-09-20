# Caddie — Sub-Agent Model for `/caddie-ask`

## Purpose

Today, `/caddie-ask` runs as a single Claude Code session that clarifies
the question, writes the plan, authors and runs every query, decides
whether to continue or revise, and writes the final answer — all in
one context window, using one undifferentiated set of instructions
(`.claude/skills/caddie-ask/SKILL.md`).

This document specifies splitting that into two [Claude Code
sub-agents](https://code.claude.com/docs/en/sub-agents), each scoped
to a distinct role:

- **lead-analyst** — turns a business question into an analysis plan,
  and turns query results back into a structured, decision-relevant
  answer.
- **data-analyst** — turns one plan step into a working query against
  the active connector, executes it, and reports back a structured
  result.

The top-level `/caddie-ask` skill becomes an orchestrator: it manages
the overall flow, makes sure each `caddie` CLI step actually happens,
and makes sure the right agent (and the right analytics skill, via
that agent) is doing each piece of work. It is the only thing that
talks to the `caddie` CLI. Interpreting results and writing the final
answer is `lead-analyst`'s job, not the orchestrator's — see Agent 1
and Orchestration below. See Spawning constraints below for the rules
that shape how agents get re-invoked.

## Spawning constraints

Three rules, all non-negotiable for this design:

- **No agent may spawn another agent.** `lead-analyst.md` and
  `data-analyst.md` must not list `Agent` (or `Task`) in their tools —
  enforced by the sub-agent's own tool restriction, not by
  instruction. Neither agent can delegate, escalate, or fan out; every
  spawn decision stays with the orchestrator.
- **An agent may be invoked more than once per episode, but never
  concurrently with itself.** Each call to a given agent must
  complete and return before the orchestrator issues that agent's next
  call. `lead-analyst` is normally called twice per episode — once to
  plan, once to interpret `data-analyst`'s results and write the final
  answer — and `data-analyst` is called once. This is still a
  materially different shape from a ping-pong loop between the two
  agents: there's no mid-episode round trip where `data-analyst`'s
  partial progress goes back to `lead-analyst` for a revised plan and
  then back to `data-analyst` again. Each of `lead-analyst`'s two calls
  is still self-contained and one-directional — plan, then (once,
  after `data-analyst` fully returns) interpret. See Orchestration
  below for how this reshapes the flow.
- **Sub-agents run at the same model and reasoning effort as the
  orchestrator.** `lead-analyst` and `data-analyst` are not configured
  with a cheaper or different model than whatever the orchestrator
  itself is running as. See Open questions (Model choice per agent) for
  why this was decided rather than left open.
- **Every call is a fresh, stateless spawn — no context carries over
  automatically.** Each of the three calls (`lead-analyst` plan,
  `data-analyst` run, `lead-analyst` interpret) starts with no memory
  of any other call, including `lead-analyst`'s own earlier plan call.
  The orchestrator is responsible for including everything a call
  needs directly in that call's prompt: the interpretation call gets
  the plan text verbatim (as returned by the planning call) plus
  `data-analyst`'s consolidated report, not a reference to "the plan
  from earlier." This is a deliberate choice over resuming the
  planning call's agent session for the interpretation step — a
  resumed session would carry the plan forward for free, but it would
  mean the orchestrator holds an agent session open across the entire
  `data-analyst` run, a different lifecycle than "spawn, get a result,
  move on." Keeping every call self-contained and stateless is
  consistent with how the rest of this design treats agent
  invocations, at the cost of the orchestrator re-passing text it
  already has on hand.

## Motivation

Two separate benefits, not one:

- **Context hygiene.** Every failed query attempt, every raw preview
  row, every "let me try a different join" — all of that currently
  lives in the same transcript the user sees. A sub-agent's internal
  turns are not shown to the user; only what it returns to the caller
  is. Moving query execution into a sub-agent means the user-visible
  conversation shows the plan, the outcome of each step, and the
  answer — not the trial and error to get there. This is a direct,
  stronger version of the existing `caddie-ask` rule "never paste raw
  preview rows into chat" — instead of remembering not to paste them,
  they're never in the visible context to begin with.
- **Specialization.** A single instruction file today has to cover
  clarifying ambiguous questions, writing an analysis plan, judging
  when a chart earns its place, writing SQL/Python against a
  connector, debugging a failed query, and writing an interpretive
  answer. These are different skills with different failure modes.
  Splitting them means each agent's system prompt and tool access can
  be tuned to what it actually does, instead of one prompt trying to
  be good at everything at once. Model and reasoning effort are not
  part of that tuning — see Spawning constraints — both agents match
  the orchestrator.

## Non-goals for this pass

- Changing the CLI (`notebook-start`/`notebook-plan`/`notebook-step`/
  `notebook-answer`) or the notebook/marimo lifecycle. Sub-agents
  change who calls these commands and when, not what the commands do.
- Changing the analytics-skill or connector plugin interfaces
  (`.specs/requirements.md`). Both agents still consume them exactly
  as `/caddie-ask` does today.
- Multi-org tuning of agent prompts. Like the analytics skill, an org
  may eventually want to customize `lead-analyst.md` or
  `data-analyst.md`; that's a future extension of the same pattern
  used for analytics skills (`skill_repo`), not part of this pass.
- Solving connector session lifecycle across sub-agent invocations
  (see Open Questions) beyond identifying it as the blocking design
  question.

## Agent 1: `lead-analyst`

**Role.** The business-facing half of the analysis: converts a
question into a complete plan up front, then, once execution is done,
turns the results into an answer. Never writes or runs a query itself.

**Defined in** `.claude/agents/lead-analyst.md`, with restricted tools
— it needs the `Skill` tool (to invoke the org's analytics skill for
grounding), `Read` for prior notebook/episode context, and (dev mode
only) `Write` scoped to `<project_dir>/logs/` — but no `Bash`, no
connector access, and no `Agent`/`Task` (see Spawning constraints).

**Invoked by the orchestrator twice per episode** — a planning call
before `data-analyst` runs, and an interpretation call after it
returns. Each call is self-contained; there's no mid-episode round
trip where `data-analyst`'s partial progress comes back for a revised
plan:

- **Clarify** (planning call). Decide what's genuinely ambiguous (time
  range, segment, granularity, the decision the answer needs to
  support) and return clarifying questions for the orchestrator to ask
  the user, if any — the orchestrator asks and folds the answers back
  into the same eventual planning call (i.e., clarification happens
  before this call is actually issued, not as a separate call to the
  agent).
- **Plan** (planning call). Invoke the configured analytics skill for
  table/column grounding, then return an ordered list of anticipated
  steps (each with a one-line description and what it's meant to
  establish) plus **contingencies**: for each step, what a surprising
  or failing result would imply and how `data-analyst` should adapt
  without needing to ask anyone (e.g. "if `enrollment` has no `region`
  column, check `enrollment_geo` instead and note the substitution";
  "if this returns zero rows, that likely means the segment filter is
  wrong, not that the answer is zero — try without it and flag the
  discrepancy"). `data-analyst` never gets a mid-run check-in with
  `lead-analyst`, so the plan still needs to anticipate failure modes
  up front, not just the happy path.
- **Interpret** (interpretation call, after `data-analyst` returns).
  Given the plan it wrote and `data-analyst`'s consolidated report,
  `lead-analyst` writes the final natural-language answer — a number,
  a short table, whatever the question needs, addressing the decision
  the plan identified. If `data-analyst` hit an uncovered deviation
  before finishing, `lead-analyst` answers from what's available with
  an explicit caveat, the same standard `caddie-ask/SKILL.md` already
  uses today. This restores
  `lead-analyst`'s specialized interpretation voice on the final answer
  — the orchestrator only relays what this call returns, it doesn't
  synthesize anything itself.

**What it must never do:** write SQL/Python, call the connector, or
spawn another agent. Its plan is the only channel through which its
planning-time judgment reaches `data-analyst` — there is no check-in
mid-run, so the plan needs to anticipate failure modes, not just the
happy path.

## Agent 2: `data-analyst`

**Role.** Executes the entire plan end to end in one continuous run —
every step, not just one — deciding for itself how to retry or adapt
within the bounds `lead-analyst`'s contingencies gave it. Never decides
whether the overall analysis is done or writes the final answer.

**Defined in** `.claude/agents/data-analyst.md`, with `Bash` access
(to run `caddie notebook-step` repeatedly), the `Skill` tool (for the
same analytics-skill grounding `lead-analyst` used to write the plan —
schema/column detail matters more here than at planning time), and
(dev mode only) `Write` scoped to `<project_dir>/logs/`. No
`Agent`/`Task` (see Spawning constraints).

**Invoked by the orchestrator exactly once per episode**, with the
full plan (including contingencies) and the project/episode
identifiers. ~~and the step cap (4)~~ **The step cap was later removed
entirely** (`.specs/requirements-marimo-pair.md`, "Batch cap removed")
— `data-analyst` now runs the whole plan with no artificial limit,
stopping only at an uncovered deviation. Within that single invocation,
the agent:

- Works through the plan's steps in order, authoring and running each
  one via `caddie notebook-step --project <slug> --episode <N>
  --description "<step description>"`, adding a chart step only when
  the plan calls for one.
- On a failed or surprising result, applies the plan's contingency for
  that step rather than stopping or guessing fresh — this is what
  replaces the mid-episode "revise the plan" round trip that a
  ping-pong design would have used a second `lead-analyst` call for.
  A deviation not covered by any contingency is not something
  `data-analyst` should improvise its way around — it stops there and
  reports the mismatch rather than guessing at a plan change nothing
  authorized.
- ~~Stops at the step cap regardless of whether the plan is "done"~~ —
  no cap anymore; runs every step in the plan, stopping early only at
  an uncovered deviation.
- Returns one consolidated report covering every step it ran: for
  each, rows/columns, the preview (bounded per the existing
  `--preview-rows` cap) or chart description, whether it succeeded,
  applied a contingency, or failed, and — since there's no
  `lead-analyst` call left to do it — a plain factual summary of what
  each result shows (not a business interpretation, just "this step
  returned 1,204 rows, enrollment count by region for Q1").

**What it must never do:** decide the analysis is complete, invent a
plan change not covered by a stated contingency, write the notebook's
final answer cell, or spawn another agent.

## Orchestration: revised `/caddie-ask` flow

The top-level `caddie-ask` skill keeps the CLI-calling responsibility
it has today (`notebook-start`, `notebook-plan`, `notebook-answer`,
rendering, opening the file). It does not synthesize the answer
itself — that's `lead-analyst`'s job, via a second call once
`data-analyst` returns:

1. Read `caddie.yaml`, determine target project/episode — unchanged.
   Generate one run timestamp for this episode's dev-mode log
   filenames (see Dev-mode activity logs), even if dev mode is off.
2. Resolve any genuinely ambiguous clarifying questions with the user
   directly (a plain conversational exchange in the orchestrator's own
   turn — not a sub-agent call).
3. Call `lead-analyst` (planning call), with the clarified question. It
   returns the plan (steps + contingencies).
4. `caddie notebook-start`, then `caddie notebook-plan` with that plan
   text.
5. Call `data-analyst` once, with the full plan. It runs every step
   (applying contingencies as needed, stopping only at an uncovered
   deviation) and returns one consolidated report.
6. Call `lead-analyst` again (interpretation call — the plan-writing
   call has already returned, so this honors the "never concurrently
   with itself" rule in Spawning constraints). This is a fresh spawn
   with no memory of the planning call, so the orchestrator includes
   the plan text it got back in step 3 and `data-analyst`'s
   consolidated report verbatim in this call's prompt (see Spawning
   constraints, Every call is a fresh, stateless spawn). It writes the
   final
   natural-language answer — a number, a short table, whatever the
   question needs, addressing the decision its own plan identified. If
   `data-analyst` hit an uncovered deviation before finishing,
   `lead-analyst` answers from what's available with an explicit
   caveat, the same standard `caddie-ask/SKILL.md` already uses today.
7. `caddie notebook-answer` with that answer text.
8. Render, open, and relay to the user — unchanged from today's steps
   9–10.

A plan that turns out to be wrong in a way `data-analyst` wasn't
authorized to work around is not something this design loops back to
fix mid-episode — it ends the episode with a caveat instead. A genuine
do-over is a new episode: a follow-up
question already starts a new episode under Caddie's existing
continuation model (`.specs/requirements.md`), so this isn't a new
limitation introduced here, just where the boundary now sits.

The user-visible transcript is the orchestrator's own turns: clarifying
questions (if any), the plan, a one-line note per step as
`data-analyst`'s consolidated report comes back, a note if a
contingency was applied, and the final answer. Everything
`data-analyst` tried and discarded, and every raw row either agent
saw, stays inside that agent's own single call.

## Dev-mode activity logs

**Problem this solves.** Per the session-lifecycle investigation above,
an inline sub-agent invocation never sends its intermediate tool calls
back to the orchestrator — only the final structured result crosses
over. That's the intended behavior (it's *why* the user-visible
transcript stays clean), but it also means that today, if
`data-analyst` tries three queries before landing on one that works,
or `lead-analyst` talks itself into revising the plan, that reasoning
is gone the moment the call returns. There's no way to go back and
check it.

**Design.** Each agent, only when dev mode is on, appends its own
activity to a plain markdown log file instead of (or in addition to)
just returning a terse summary:

- **Toggle.** Off by default. Controlled by a `dev_mode: true` setting
  in the user's `caddie.yaml` (a standing preference, consistent with
  how the rest of `caddie.yaml` works — see `.specs/requirements.md`
  Configuration), which the orchestrator reads once per episode and
  passes down to both agents as part of their invocation. Not a
  per-question flag — a user debugging Caddie itself turns it on for a
  session, not for one question.
- **Location.**
  `<project_dir>/logs/<agent-name>-<call-name>-<run-timestamp>.md`,
  alongside `notebook.py` and `.caddie_project.json` — same directory,
  same locality rules (local-only, never committed, per
  `requirements.md`'s Storage section). `<call-name>` is `plan` or
  `interpret` for `lead-analyst` (it's called twice per episode, so
  agent name and run timestamp alone would collide) and `run` for
  `data-analyst` (called once). The episode number isn't part of the
  filename — a "run" and an "episode" are already the same thing (each
  episode runs this same fixed sequence of calls once), so encoding
  both would just be redundant. The run timestamp is generated once by
  the orchestrator at the start of the episode (step 1 of Orchestration
  above) and handed to every agent call, so all three log files for the
  same run are easy to correlate by name — and, since `Write` is a
  whole-file replace, not an atomic append, giving every run its own
  timestamped file is what keeps a later re-run (e.g. `/caddie-load`
  re-executing an existing episode's steps, per
  `.specs/requirements.md`) from reopening and clobbering an earlier
  run's file.
- **Content.** The file opens with a short header identifying what
  it's a log of — project slug, episode number, agent name, run start
  time — so the log is self-describing from its content alone, not
  just its filename or directory location. That's what actually
  matters (which run, which agent), not the filename scheme. Below the
  header, each entry is a timestamped, short account of what happened,
  not a raw data dump: the query `data-analyst` tried (including ones
  it discarded before landing on a working one) and why it retried, or
  the reasoning `lead-analyst` used in writing a contingency. Preview
  rows still don't belong here — the point is reviewing *behavior and
  reasoning*, not standing up a second, uncapped output channel. If a
  file ever does end up covering more than one run (a future design
  choice, not this one), each run's entries should be preceded by a
  fresh copy of that header block and a `---` divider, so the
  boundary between runs is visible in the content itself rather than
  relying on the reader already knowing the file-splitting rule.
- **Tool access.** Both agents need `Write`, scoped to `<project_dir>/
  logs/` only — `lead-analyst` doesn't otherwise have write access to
  anything (see its tool list above), and this shouldn't become a back
  door to editing the notebook itself.
- **Failure mode.** A missed or failed log write is a soft failure —
  it never blocks or degrades the actual analysis. Dev logs are a
  debugging aid, not part of the product.
- **Relationship to Claude Code's own session tooling.** This doesn't
  replace `claude attach`/`claude logs` (see the sub-agent-visibility
  discussion above) — it's a separate, Caddie-owned mechanism that
  works the same regardless of whether an agent ran as an inline call
  or a background session, and the file persists after the Claude Code
  session itself ends, which an attached session's live view doesn't.

## Open questions

- ~~**Connector session lifecycle across calls.**~~ Resolved by
  reading the current implementation: `.specs/requirements.md`
  states `/caddie-ask` runs in-process specifically to share a live
  connector session across steps, but `notebook-step.py` (line 89)
  actually calls `load_connector(...)` fresh on every invocation, and
  `DatabricksConnector._session` (`databricks.py`) starts `None` and
  is rebuilt per process — there is no session shared across steps
  today. Each `caddie notebook-step` call is already an independent
  reconnect. This means handing each step to a separate `data-analyst`
  sub-agent invocation introduces no new session-lifecycle problem: it
  reconnects exactly as often as the current single-session design
  already does. (The stated rationale in `requirements.md` should be
  corrected or the connector should actually be made to persist a
  session across steps — a separate, pre-existing discrepancy, not one
  introduced by this design.)
- ~~**Loss of `lead-analyst`'s interpretation voice on the final
  answer.**~~ Resolved: `lead-analyst` is called twice per episode (see
  Spawning constraints, Agent 1, and Orchestration above) — once to
  plan, once to interpret `data-analyst`'s results and write the final
  answer itself. The orchestrator only relays that answer; it doesn't
  synthesize anything. This was the original two-call design's
  behavior and is restored here rather than worked around.
- **Contingency coverage.** `data-analyst` is only as good as the
  contingencies `lead-analyst` wrote into the plan — an uncovered
  deviation makes it stop and report rather than improvise, which is
  the safe failure mode, but it also means a plan with thin
  contingencies will hit that wall more often than the old ping-pong
  design would have. Worth watching whether `lead-analyst` is actually
  writing useful contingencies in practice, not just a rote list of
  steps.
- **Iteration cost and latency.** Three sub-agent calls per episode —
  `lead-analyst` plan, `data-analyst` run, `lead-analyst` interpret —
  down from up to 8+ in the earlier ping-pong design. `data-analyst`'s
  single call now has to run every step itself in one continuous
  session, so its own latency is closer to what today's single-session
  `/caddie-ask` already takes — worth confirming against real episodes
  rather than
  assuming.
- ~~**Model choice per agent.**~~ Decided: both sub-agents run at the
  same model and reasoning effort as the orchestrator (see Spawning
  constraints above), rather than tuning `data-analyst` to a cheaper
  model. A cheaper `data-analyst` producing worse queries would
  undermine the point of the split, and this isn't being revisited
  without evidence from real episodes that it's safe.
- **Failure surfacing.** `data-analyst`'s consolidated report needs a
  clear, structured shape for "succeeded," "succeeded via
  contingency," and "failed/stopped" per step, since `lead-analyst`'s
  interpretation call is what reads that report and decides whether to
  answer with a caveat — the same "conclude with a caveat" standard
  `caddie-ask/SKILL.md` already uses today.
- **Org-specific tuning.** Whether `lead-analyst.md`/`data-analyst.md`
  should eventually be overridable per org (the same way `skill_repo`
  lets an org supply its own analytics skill) is out of scope here,
  but the naming/location should probably anticipate it rather than
  assume Caddie core's copy is always final.

## Relationship to existing interfaces

Neither the analytics-skill interface nor the connector-plugin
interface changes. `lead-analyst` invokes the analytics skill for
planning grounding the same way `caddie-ask` does today; `data-analyst`
invokes it again for query-writing grounding (schema/column detail
matters more at that point than at planning time). The connector is
still only ever touched through `caddie notebook-step`, never
imported directly by an agent.
