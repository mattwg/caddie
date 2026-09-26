# Caddie — cost tracking

## Purpose

Every Caddie notebook (`/caddie:ask` episodes, `/caddie:explore` steps)
has no visibility into what it cost to produce. This adds a `costs`
cell, kept pinned to the bottom of the notebook, tracking cumulative
token spend across every `/ask` episode and `/explore` instruction that
ever touched the project — including ones that happen in a different
Claude Code session than the one that started it, since a project can
be resumed days later.

## Why not just read Claude Code's own cost data

- Claude Code occasionally writes a `type: "cost-state"` entry (with an
  already-computed `totalCostUSD`) into a session's transcript JSONL,
  but it's sparse — observed twice in a 92-turn session, seemingly tied
  to session pause/exit rather than any per-turn event. Too sparse to
  build a deterministic hook around.
- Per-message token usage (`message.usage`, on every `type: "assistant"`
  transcript entry) is always present. This is what community tools
  like `ccusage` fall back to in their "calculate" mode, and what this
  design uses: sum tokens by model, price them from a maintained table
  (`caddie.cost.pricing`).
- That table has a bundled floor (Anthropic's published rates, hand-
  updated) plus an optional network refresh: whenever a session starts
  tracking a project (`caddie track-observe`/`track-start` - see
  Design below, not the `Stop` hook) best-effort fetches LiteLLM's
  `model_prices_and_context_window.json` and caches
  whatever it finds under a bare `claude-...` key — confirmed by
  fetching the real file that this is the exact string shape Claude
  Code's own transcripts use in `message.model` (no provider prefix or
  `@date`/`-v1:0` suffix to normalize away), so it's an exact lookup,
  not fuzzy matching. Any failure (offline, timeout, upstream format
  change) leaves the existing cache — or, absent one, the bundled
  table — in effect; `price()` never raises over a pricing gap, it
  reports `usd=None` for a model in neither.
- Subagent calls (exactly how `/caddie:ask` invokes `lead-analyst` and
  `data-analyst`, via the `Agent`/Task tool) never appear inline in the
  parent transcript — they land in sibling files at
  `<session_dir>/<session_id>/subagents/agent-*.jsonl`. Any accounting
  for an `/ask` episode has to read these too, or it only counts the
  orchestrating turn and misses most of the actual cost.

## Design

Deterministic, not agentic — the LLM does not compute or write cost
data itself, and doesn't even need to know cost tracking exists. Two
hooks, both in `hooks/hooks.json`:

1. **`caddie track-observe`**: a `PostToolUse` hook matching `Bash`.
   `caddie notebook-start` and `caddie notebook-edit` (the two commands
   that create or open a project, already called by `/caddie:ask` and
   `/caddie:explore` for their own reasons) print the notebook's
   absolute path to stdout (`notebook: <path>` /
   `file: <path>` respectively) - `PostToolUse`'s hook input carries
   that stdout verbatim as `tool_response.stdout`. `track-observe`
   matches the command, extracts the path, and writes a small marker,
   `~/.caddie/state/session-<session_id>.json`, naming the project
   (`path.parent`). No skill instruction calls anything cost-related at
   all - this was the original design's one deliberately-added skill
   step (`caddie track-start --project <slug>`), replaced once it was
   clear the information it needed was already flowing through a tool
   call the skills make anyway. `track-start` still exists as the
   manual/scriptable equivalent, for testing or a future caller that
   doesn't go through `notebook-start`/`notebook-edit`.

2. **`caddie track-update`**: wired up as a `Stop` hook
   (`hooks/hooks.json`, fires once per top-level Claude Code turn —
   which lines up with exactly one `/ask` episode or one `/explore`
   instruction, since nested subagent calls happen inside that same
   turn). Reads the hook's stdin JSON (`session_id`, `transcript_path`).
   Fast no-op if no marker matches the session (most `Stop` events are
   unrelated to Caddie). If a marker matches:
   - Reads new usage since this (project, session)'s last known cursor
     (`caddie.cost.transcript.episode_usage`) from the main transcript
     plus any not-yet-seen subagent files.
   - Prices it (`caddie.cost.pricing`) and folds it into the project's
     sidecar (`.caddie_project.json`'s `costs` field —
     `caddie.notebook.state.ProjectState`), keyed by model and by
     session, so totals accumulate across every session that ever
     touched the project.
   - Copies the full session transcript (main file + `subagents/`) into
     `<project_dir>/.transcripts/`, overwriting each time. Hidden
     directory, same treatment as `.caddie_project.json` — raw session
     data kept alongside the notebook, not notebook content.
   - Pushes a freshly-rendered `costs` cell into the live notebook, if
     one is paired (`caddie.cost.kernel`, talking directly to marimo's
     HTTP API the same way `marimo-pair`'s `execute-code.sh` does — no
     LLM call involved). Delete-then-recreate rather than edit-in-place,
     so the cell always ends up last even as later episodes/steps
     append cells after it. If no kernel session is reachable, this
     step alone is skipped — the sidecar and transcript copy already
     landed, and the next successful update reflects the full total.

## Non-goals

- No network call from the `Stop` hook itself (`track-update`) — it
  must stay fast and offline-safe on every turn. The pricing refresh
  only happens from `track-start`, once per episode/step.
- No attempt to reconcile with Claude Code's own billing/`/cost`
  output; this is caddie's own best-effort estimate, clearly labeled as
  such in the rendered cell.
- Doesn't change anything about `lead-analyst`/`data-analyst`'s
  spawning rules, plan shape, or the marimo-pairing mechanism itself
  (`.specs/requirements-marimo-pair.md`), and doesn't add any
  instruction to either skill at all — both hooks run independently,
  triggered by tool calls and turn boundaries the skills already
  produce for unrelated reasons.

## Open questions

- **Hook commands can't assume `caddie` is on `PATH`.** Confirmed live:
  a GUI-launched Claude Code session's hook subprocess did not inherit
  the same `PATH` this repo's own interactive shell has, so a bare
  `"command": "caddie track-observe"` silently no-op'd (command not
  found is a non-blocking hook error - never surfaced, `~/.caddie/state/`
  simply never got created). `hooks/hooks.json` now resolves the
  binary itself (`command -v caddie`, falling back to `uv`'s default
  `~/.local/bin/caddie`) and logs stderr to
  `~/.caddie/state/hooks.log` for exactly this kind of silent failure
  going forward. Also confirmed: plugin-provided hook registration
  (`hooks/hooks.json`) appears to be read once per app process launch,
  not per new session/conversation - editing the file and starting a
  new session in the same running app instance did not pick it up;
  fully quitting and relaunching did.
- **Stability of the `cm` delete/create-cell shape.** Same caveat as
  `.specs/requirements-marimo-pair.md`: `marimo._code_mode` is a
  private, unstable API. `caddie.cost.kernel` was written against the
  method names `marimo-pair`'s own `SKILL.md` documents
  (`create_cell`/`edit_cell`/`run_cell`/`delete_cell`), not verified
  against a live `help(cm)` at the time this was written — confirm on
  first real run.
- **Bedrock/Vertex pricing drift.** The bundled pricing table uses
  Anthropic's first-party per-token rates; an org running through
  Bedrock or another partner platform with a negotiated discount will
  see caddie's estimate diverge from their actual bill.
- **Trusting a community-maintained catalog.** LiteLLM's pricing file
  is not an Anthropic-operated source — it could lag a brand-new model
  release, or (less likely, given the exact-key match) drift from
  Anthropic's own numbers without anyone at caddie noticing. The
  bundled table is the fallback of record if this ever needs
  reverting; `pricing-cache.json`'s `source`/`fetched_at` fields are
  there so a wrong number can be traced back to when/where it came
  from.
