# Caddie — `data-analyst` execution via marimo pair (Code Mode)

## Purpose

Today, per `.specs/requirements-subagents.md`, `data-analyst` executes
each plan step as one stateless CLI call:
`caddie notebook-step --project <slug> --episode <N> ...`, code on
stdin. Every query it runs — the real step *and* anything it runs
along the way to get there (does this column exist, roughly how many
rows, which of two tables has the field) — goes through that same
call, and every call permanently appends a cell to `notebook.py`
(`.specs/todo.md`: "avoid leaving debug cells in notebook"). There is
no way to fix a step in place once it's written wrong; the only
remedies today are appending a new step and leaving the broken one
behind, or hand-editing `notebook.py`'s raw text (which
`data-analyst.md`'s current "Long-running commands" section already
resorts to for a "broken or leftover cell"). And because
`execute_and_summarize` just calls `connector.execute(code)` fresh
each time (confirmed in `notebook/executor.py`), inspecting an earlier
step's result means re-running its query against the warehouse, not
reading the value that's already sitting in the kernel.

marimo ships a purpose-built answer to exactly this: **marimo pair**
(also called Code Mode), an agent skill marimo itself distributes
(`npx skills add marimo-team/marimo-pair`, bundled inside the `marimo`
package at `_server/ai/skills/marimo-pair/SKILL.md`), built for
Claude Code, Codex, and OpenCode. It attaches an agent to a *live*
`marimo edit` kernel and gives it a scratchpad for read-only
exploration plus a `marimo._code_mode` (`cm`) API for durable,
DAG-validated cell changes. This document specifies moving
`data-analyst`'s step-execution mechanism from `caddie notebook-step`
onto marimo pair.

## Motivation

- **No debug cells left behind.** Scratchpad execution (`execute_code`
  in marimo pair) runs Python against a copy of the kernel's globals
  and never touches the notebook's cells or dataflow graph. Checking
  something along the way stops requiring a permanent, visible step.
- **Cheap inspection of prior results.** The scratchpad can read
  `result_2_3` (or any other notebook global) by name, directly from
  the live kernel — no re-querying the warehouse just to look at a
  value that's already been computed this session.
- **Real fix-in-place.** `cm.edit_cell(cid, new_code)` mutates a
  specific cell, validated against marimo's DAG contract (no cycles,
  one owning cell per public name) before it's committed. This
  replaces both current workarounds — "append a new step and leave the
  broken one" and "hand-edit `notebook.py`'s raw text" — with the
  mechanism marimo itself considers safe for a live notebook.
- **Real removal of a step that turns out to be exploratory in
  hindsight**, via `cm.delete_cell` after checking
  `ctx.graph.descendants(cid)` for blast radius — `cm` is the
  documented, marimo-native version of the direct-file-surgery cleanup
  step already asked for in this project (`.specs/todo.md`: "avoid
  leaving debug cells in notebook").
- **This is marimo's own recommended integration path**, not a
  bespoke MCP client caddie would have to build and maintain — per
  marimo's docs, marimo pair is "the recommended way to collaborate on
  marimo notebooks with agents." It's delivered as a skill, the same
  mechanism `data-analyst` already uses for org analytics skills, so
  it fits caddie's existing tool model rather than requiring a new
  tool type.

## Non-goals for this pass

- `lead-analyst`'s role, the plan/interpret call shape, and the
  spawning constraints in `.specs/requirements-subagents.md` — all
  unchanged. This document only changes *how* `data-analyst` executes
  a step, not who calls it, how often, or what it's given.
- The analytics-skill interface and connector-plugin interface
  (`.specs/requirements.md`) — unchanged. `data-analyst` still invokes
  the analytics skill for schema/column grounding exactly as today.
- ~~`notebook-start`, `notebook-plan`, and `notebook-answer` — unchanged,
  stay pure file operations~~ **Superseded, see Scope below.** Only
  `notebook-start` stays a pure file operation (no kernel exists yet
  when it runs). `notebook-plan` and `notebook-answer`'s *cell writes*
  move to the paired kernel too, for a reason this pass's first
  implementation didn't anticipate: this same document already decided
  the paired kernel persists across the orchestrator's whole episode,
  not just `data-analyst`'s own calls — which means one is normally
  still alive by the time `notebook-answer` would run, and a direct
  file write while a live kernel holds a stale copy is exactly the
  clobber scenario `caddie-edit`'s own caveat warns about. This was
  confirmed live, not theoretical: a stale kernel from before this
  scope expansion silently overwrote a `notebook-answer` write once
  already. `notebook-answer`'s render step (`marimo export html`) is
  unaffected and split out into its own CLI command,
  `caddie notebook-render`, so writing the answer cell via pairing
  doesn't also re-trigger `append_answer`'s one-answer-per-episode
  check.
- ~~`/caddie-load`'s bulk re-execution path (`notebook-rerun`/
  `rerun.py`) — out of scope~~ **Reopened, see Open questions**: it now
  pairs too, for the same reason `notebook-answer` did.
- The dev-mode activity log design
  (`.specs/requirements-subagents.md`, Dev-mode activity logs) —
  unaffected, still a `Write`-scoped file under `<project_dir>/logs/`.
- Multi-org tuning of `data-analyst.md` beyond what
  `.specs/requirements-subagents.md` already scoped out.

## Scope: which lifecycle stage moves to a live kernel

**Revised twice from this document's first draft**, after running real
episodes surfaced first the `notebook-answer` clobber bug, then a
narrower version of the same bug in `notebook-start` itself: it's not
just `data-analyst`'s step execution that moves to the live kernel —
it's everything written into the notebook for an episode, once a
kernel exists for that project. Only a brand-new project has no kernel
yet; every later episode in that same project does.

- **A brand-new project's first episode**: `caddie notebook-start`
  creates the notebook file (`setup` cell, PEP 723 header,
  `question_1`) as a plain file operation, since nothing can pair with
  a kernel that has nothing to attach to yet. This is the one write in
  the whole system with no live-kernel alternative, and
  `builder.start_episode` now enforces it structurally — it raises if
  the notebook already exists, rather than silently supporting the
  append-a-question-to-an-existing-project case it used to.
- **Every later episode in that same project** (a `/caddie-ask`
  continuation, or `/caddie-load` bringing an existing project back):
  a kernel already exists (the shared workspace server persists across
  episodes), so the orchestrator pairs with it *first*
  (`.claude/skills/caddie-ask/SKILL.md`'s "Pairing with the notebook's
  kernel") and writes the new `question_{E}` cell through it. Calling
  `notebook-start` again here would race whatever kernel is already
  attached to that file - confirmed live as a second occurrence of the
  same clobber pattern `notebook-answer` hit first.
- **Plan and answer cells** (`plan_{E}`, `answer_{E}`) are written by
  the orchestrator through that same paired kernel — a scratchpad
  `execute-code.sh` call using `cm.get_context()`. `notebook-plan` and
  `notebook-answer` (the CLI commands that used to write these
  directly) have been removed entirely, along with `notebook-step` and
  `notebook-rerun` and everything in `notebook/builder.py`/`executor.py`
  that only existed to support them - once pairing is the only way
  data-analyst, the orchestrator, and `/caddie-load` write anything,
  keeping a second, unused file-writing code path around was pure
  surface area, not a fallback worth preserving.
- `notebook-answer`'s render step is unaffected in substance but lives
  in its own command now, `caddie notebook-render` (a thin wrapper
  around the same `render_notebook`), called once the answer cell is
  confirmed written.
- `data-analyst`'s own step execution is unchanged from this document's
  original scope in mechanism: still moves from N stateless CLI
  invocations to one live-kernel pairing session. **Later revised**:
  that one session now covers the *whole plan*, not a capped batch of
  it — see "Batch cap removed" below.
- `/caddie-load`'s re-execution also pairs now (see the reopened Open
  Question below) rather than calling `notebook-rerun`, which no longer
  exists.

So across a project's whole lifetime, exactly one write is ever a plain
file operation - the very first episode's `notebook-start` - and
everything after it, in every later episode, goes through whatever
kernel is already paired for that project.

## New requirement: a live kernel to attach to

marimo pair only works against a running, `--no-token` `marimo edit`
server with an active browser session attached; there is nothing to
pair with otherwise. Concretely, this needs:

- **Reusing `caddie notebook-edit`**, which already finds-or-starts an
  edit server for a project (`notebook/edit.py`) — this doesn't invent
  a new server-management command, and its existing
  `marimo edit <nb_path> --headless --no-token --sandbox` invocation
  doesn't need any new flag. **Correction from this document's first
  draft:** the maintained `marimo-team/marimo-pair` skill does not use
  marimo's MCP server at all (that's a different, MCP-based mechanism
  bundled separately inside the `marimo` pip package itself, at
  `marimo._server.ai.skills.marimo-pair` — a mistake this document
  originally followed). The real skill's `execute-code.sh`/
  `discover-servers.sh` scripts talk directly to marimo's own HTTP API
  (`/api/sessions`, `/api/kernel/execute`), so there is no `--mcp`
  flag, no `marimo[mcp]` dependency, and no Claude Code MCP
  registration involved anywhere in this design. See "Confirmed
  blocker, then resolved" under Open questions for why this mattered.
- **An active browser session**, which `execute-code.sh` requires to
  target a kernel (marimo's own docs: "The notebook UI must be open in
  a browser... If running headless, give the user the local URL and
  wait for them to open it"). Since `data-analyst` runs unattended,
  `notebook-edit` opens the URL itself (`webbrowser.open`) whenever no
  session exists yet, rather than waiting for a human — the same thing
  a human running `/caddie-edit` would otherwise do by hand.
- **The `marimo-pair` skill itself**, present as a project skill at
  `.claude/skills/marimo-pair` (the actual `marimo-team/marimo-pair`
  GitHub repo's content: `SKILL.md` plus `scripts/discover-servers.sh`,
  `scripts/execute-code.sh`, and `reference/*.md`) that `data-analyst`
  invokes through its existing `Skill` tool access — no new tool type
  needed, and (unlike the original MCP-based draft of this plan) no
  dynamic registration step of any kind. It's not vendored into this
  repo's git history: `caddie install`/`caddie update` fetch it fresh
  via `caddie.install.marimo_pair` (`uvx deno -A npm:skills add|upgrade
  marimo-team/marimo-pair` — `uvx` rather than `npx`, since caddie
  already depends on `uv` and this avoids a separate Node/`npx`
  toolchain requirement). The `skills` CLI writes the actual skill
  content under `.agents/skills/` (its universal, tool-agnostic
  layout, shared across Codex/Amp/Antigravity/etc.) and symlinks
  `.claude/skills/marimo-pair` to it — both are gitignored, so a stale
  hand-copied snapshot can't drift from upstream. It also installs a
  bundled `retro-marimo-pair` skill from the same source, handled the
  same way. What *is* committed is `skills-lock.json` (repo root), the
  CLI's lockfile pinning each skill's resolved content hash — that's
  what makes an upstream version bump a reviewable diff instead of a
  silent change on whichever machine happens to run `caddie
  update` next.

### One shared server per user, not one per project

**Second correction from this document's first draft**, found only
after running real episodes: the original design had `notebook-edit`
launch `marimo edit <one-project's-notebook.py> --sandbox` per project.
Every `/caddie-ask`, `/caddie-load`, or `/caddie-edit` invocation for a
*different* project therefore started a brand-new server process, and
nothing ever stopped one — after a handful of sessions, seven separate
`marimo edit` processes (each with its own `--sandbox` resolve) were
found still running for seven different projects, none of them
reachable or needed anymore except the one actively in use.

marimo itself already solves this: pointing `marimo edit` at a
*directory* instead of a single file, still with `--sandbox`, puts it
in `SandboxMode.MULTI` (`marimo._cli.sandbox`) — "multi-file sandbox:
IPC kernels with per-notebook sandboxed venvs." One long-running server
process then hosts every notebook under that directory, and each one
still gets its own isolated per-notebook `uv` environment resolved from
its own PEP 723 header — per-notebook *dependency* isolation
(`.specs/requirements.md`) is unaffected, only the *server process*
becomes shared. `notebook-edit` now points at
`<notebooks_root>/<username>/` (the whole user's workspace) rather than
one project's file, needs the `marimo[sandbox]` extra (`pyzmq`) in
caddie's own `pyproject.toml` (stripped back off before it reaches a
per-notebook header — see `notebook/dependencies.py`), and every caller
now addresses a specific notebook within that shared server by file
path: `execute-code.sh --file <path>` for pairing, and
`?filename=<path>&view-as=present` in the URL a human opens via
`/caddie-edit` (confirmed against marimo's bundled frontend JS,
`FilenameState.getFilename`/`setSearchParam`, and live-tested: opening
a second project's notebook while the first's session was still active
correctly reused the one running server and opened the second file
alongside it).

This still doesn't fully solve unbounded accumulation — one shared
server per user just replaces N per-project servers with 1, and that 1
still never stops on its own. An idle-timeout follow-up (marimo's own
`--timeout` flag) was discussed and deferred in favor of landing the
shared-server fix first; see Open questions.

## Concurrency hazard this introduces

marimo pair's own `SKILL.md` states plainly: "direct file edits WILL
NOT reach the live kernel or user, and the kernel may overwrite them
on save." Two different flows can now have a live session open against
the same `notebook.py`: `data-analyst` pairing during a
`/caddie-ask` episode, and a human running `/caddie-edit`, which also
opens (or reuses) a `marimo edit` server for that project
(`.claude/skills/caddie-edit`). If both exist at once, whichever one
writes last can silently clobber the other's in-kernel state on save.

`data-analyst` should therefore **reuse an already-running edit
server for the project rather than assume it needs to start its own**
— the same behavior `caddie-edit` itself already documents ("reuses
an already-running server for that notebook instead of starting a
duplicate"). `notebook-edit`'s existing find-before-start logic
already does this; pairing on top of it doesn't change that behavior,
but the two flows need to actually agree on one shared session instead
of independently believing they own it. What should happen if a human
has `/caddie-edit` open on a project *while* `/caddie-ask` is running
for it is an open question below, not resolved by "reuse the server"
alone.

## Agent 2 revised: `data-analyst` (execution model, not role)

This section covers `data-analyst`'s own step execution specifically;
see "Scope" above for the parallel (and, chronologically, later-added)
change to the `caddie-ask` orchestrator's own plan/answer writes, which
follows the identical pairing mechanism one level up.

Still invoked once per episode by the orchestrator with the full plan
and contingencies, exactly as `.specs/requirements-subagents.md`
specifies — that call shape doesn't change. What changes is only how
it carries out each step, inside that one call:

- Before running any step, it ensures a paired kernel session exists
  for the project (via `caddie notebook-edit`, reusing a running
  server per the concurrency note above) and invokes `marimo-pair`.
- Per marimo pair's own protocol, its first action in that session is
  the required inspection call alone —
  `import marimo._code_mode as cm; help(cm)` — before any other `cm`
  usage, to confirm the API shape of whatever marimo version is
  actually running.
- **A real plan step** (the query/chart that belongs in the final
  notebook) is added via `cm.create_cell` + `cm.run_cell`, writing the
  same `description_{E}_{S}` / `code_{E}_{S}` (or `chart_{E}_{S}`) /
  `output_{E}_{S}` cell shape `builder.py`'s `append_step` already
  produces today, so the notebook's own structure and step-numbering
  convention (`.specs/requirements-subagents.md`) don't change even
  though what writes them does.
- **A check along the way** (does this column exist, roughly how many
  rows, which table has the field) runs as plain scratchpad Python via
  `execute_code` — never `cm.create_cell` — so it never becomes a
  notebook cell at all. This supersedes the current
  `data-analyst.md` guidance to run a capped, ad-hoc
  `uv run python -c "..."` script for the same purpose: pairing gives
  the same "don't pollute the notebook" outcome with real access to
  already-computed kernel state instead of a fresh, disconnected
  connector call.
- **A step that came out wrong** is fixed via
  `cm.edit_cell(cid, new_code)` in place — reading the cell's current
  body first, per marimo pair's own guidance, since another editor
  could have touched it between calls — rather than appended as a new
  step. This replaces `data-analyst.md`'s current "Long-running
  commands" guidance to hand-edit `notebook.py`'s text for a broken
  cell.
- **A step that turns out, in hindsight, to have been exploratory**
  (should not have been a real step at all) is removed via
  `cm.delete_cell`, after checking `ctx.graph.descendants(cid)` for
  blast radius, rather than the direct-file-editing cleanup currently
  specified in `data-analyst.md`'s "Keep exploration out of the final
  notebook" section — this document supersedes that section's
  mechanism, not its intent.
- Still applies `lead-analyst`'s contingencies rather than improvising
  past an uncovered deviation, still returns one consolidated report
  per call, still never decides the plan is complete, never writes the
  answer cell, and never spawns another agent — none of that changes
  from `.specs/requirements-subagents.md`. **The batch size/step cap
  itself was later removed entirely** — see "Batch cap removed" below;
  `data-analyst` now runs the whole plan in this one call rather than a
  capped slice of it.

## Tool access

`data-analyst` keeps `Bash` (still needed for `caddie notebook-start`
readiness checks, `caddie notebook-edit`, and any `uv run` prefacing)
and `Skill` gains a second real consumer — `marimo-pair`, alongside
the org's analytics skill it already invokes for grounding. No new
tool type is required; this is the main reason this integration fits
caddie's existing agent model instead of requiring a custom MCP
client.

## Open questions

- ~~**BLOCKING: a subagent can't reach an MCP server registered
  mid-session.**~~ Resolved by correcting a wrong assumption, not by
  fixing the MCP path. The first implementation of this spec had
  `caddie notebook-edit` launch `marimo edit --mcp code-mode` and
  register the resulting endpoint with Claude Code via `claude mcp
  add`. That hit a real, confirmed-live wall: a server registered
  mid-session never propagated into `data-analyst`'s own subagent tool
  registry (not even with `ToolSearch` added to its `tools:`
  frontmatter, and not fixable by restarting) — per Claude Code's own
  docs, MCP tool inheritance is documented only for servers already
  configured when a session starts, with no documented path for a
  dynamically-registered one to reach a subagent at all. Chasing that
  further turned out to be solving the wrong problem: reading the
  actual `marimo-team/marimo-pair` GitHub repo (rather than the
  differently-built, MCP-based skill vendored inside the `marimo` pip
  package at `marimo._server.ai.skills.marimo-pair`, which this
  document originally and mistakenly followed) showed the maintained
  skill uses no MCP server at all — `execute-code.sh`/
  `discover-servers.sh` are plain `Bash` scripts calling marimo's HTTP
  API directly. Since `data-analyst` already has `Bash`, there is
  nothing to register and nothing for a subagent to fail to inherit.
  See "New requirement: a live kernel to attach to" for the corrected
  mechanism. The one real requirement this surfaced instead is that
  `execute-code.sh` needs an active browser session, which
  `notebook-edit` now creates itself (`webbrowser.open`) since nothing
  else would for an unattended `data-analyst` run.
- ~~**Kernel lifetime across the orchestrator's batch/check-in
  boundary.**~~ Moot: see "Batch cap removed" below — there is no
  batch/check-in boundary mid-plan anymore, so this question no longer
  applies. The shared workspace server still persists independently
  across episodes, as originally leaned toward here.
- **Batch cap removed.** `data-analyst` originally ran the plan in
  capped batches (4 steps per call), pausing for the orchestrator to
  ask the user whether to continue after each one. That cap and the
  mid-plan check-in were removed entirely: `data-analyst` now runs the
  *entire* plan front to back in a single call, stopping early only at
  an uncovered deviation (never at an arbitrary step count). This
  simplifies `caddie-ask`'s Orchestration step 6 to one `data-analyst`
  call instead of a loop, and removes the "ask the user whether to run
  another batch" `AskUserQuestion` step entirely. The interpretation
  call (`lead-analyst`, step 7) now always sees one report, never a
  concatenation of several.
- **What happens if `/caddie-edit` is open on the same project while
  `/caddie-ask` is running.** The Concurrency hazard section above
  says the two should share one server; it doesn't say what
  `data-analyst` should do if a human is actively editing cells in
  that same session concurrently (block, warn, proceed anyway).
- **Deferred: an idle timeout on the shared workspace server.** The
  shared-server fix above (see "One shared server per user") stops the
  count of running servers from growing per-project, but the one
  server it leaves is still never stopped on its own — it'll run
  indefinitely once started, same as every per-project server did
  before it. marimo has a built-in `--timeout` flag (shut down after N
  minutes with no connection) that's a natural fit, requested and
  deferred in this same discussion so the shared-server change could
  land on its own first. Needs deciding: what timeout value, and
  whether an explicit `caddie notebook-stop` (or a `notebook-gc` style
  sweep across old servers) is also worth adding rather than relying
  on idle timeout alone.
- **Stability of a private API.** `marimo._code_mode` is documented by
  marimo itself as "a PRIVATE, UNSTABLE agent API" with no semver
  guarantee across marimo versions. What's caddie's policy if a marimo
  upgrade breaks it — pin a known-good marimo version, or fall back to
  the pre-existing `notebook-step` CLI path?
- ~~**Fallback when pairing can't be established**~~ Decided: no
  fallback for now. If pairing can't be established (extra not
  installed, server fails to start, marimo version mismatch on the
  `help(cm)` inspection call), `data-analyst` fails the run outright
  rather than falling back to any other execution path (there is no
  CLI path left to fall back to - `notebook-step` was later removed
  entirely). Revisit if running different marimo versions across orgs
  makes this too brittle in practice.
- ~~**`/caddie-load`'s re-execution path.**~~ **Reopened and reversed**
  after living with the rest of this design for a while:
  `notebook-rerun`/`rerun.py` was originally left as a bulk,
  unattended, connector-only validation pass (re-executes each step's
  code fresh, reports pass/fail, never touches the notebook's stored
  results) on the reasoning that this pass only covered an active
  `/caddie-ask` episode's own step execution. That reasoning held up
  fine as long as re-execution and pairing were two genuinely separate
  concerns, but once everything else a `/caddie-ask` episode writes
  goes through the live kernel, a `/caddie-load` that instead
  side-channels around it to validate-without-persisting started
  looking like the odd one out rather than a deliberate boundary.
  Decided: `/caddie-load` now pairs too (`.claude/skills/caddie-load/SKILL.md`),
  re-running each existing step via `cm`'s run-cell operation against
  the live kernel rather than a fresh connector call — so a reloaded
  project's notebook shows genuinely current results, not just a
  pass/fail check from whenever it was last loaded. `notebook-rerun`
  itself is unchanged and still works as a standalone CLI command
  (validate-only, no kernel needed) for any caller with no live kernel
  to pair with, same as `notebook-step`/`notebook-plan`/`notebook-answer`
  remaining available outside the orchestrated flow.
- **Whether this needs `lead-analyst`'s plan/contingency shape to
  change at all.** Current read: no — contingencies describe *what*
  to try next on a surprising result, not *how* it gets written into
  the notebook, so this should be transparent to `lead-analyst`.
  Worth confirming once implemented, not assumed.

## Relationship to existing interfaces

The analytics-skill and connector-plugin interfaces
(`.specs/requirements.md`) are unaffected: `data-analyst` still
invokes the analytics skill for schema/column grounding exactly as
today, and the connector is still never imported directly by an
agent — it's touched only by code the notebook's own cells run,
whether that code got there via a `notebook-step` CLI call or a
`cm.create_cell` call from a paired session. `.specs/
requirements-subagents.md`'s orchestration flow, spawning constraints,
and dev-mode logging are all unaffected — this document changes one
agent's execution mechanism, not the shape of an episode.
