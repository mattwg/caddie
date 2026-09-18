# Caddie — Requirements

## Purpose

Caddie is a harness, not a company-specific tool. It gives any organization a one-command way to get a working local analytics environment (Python, `uv`, notebook tooling) and to force analysis work into reusable, re-runnable notebooks instead of one-off chat queries — closer to how Delphina projects work. What question-answering logic to use and what data backend to query are both pluggable: Caddie owns the harness (install, environment, notebook lifecycle, charting), and two things are configured per organization:

- **Analytics skill** — the thing that knows how to turn a question into a query/analysis for that org's data model.
- **Data connector** — the thing that knows how to talk to that org's data backend (Databricks, Snowflake, PostgreSQL, etc.).

Neither is hardcoded into the harness. Databricks is the first concrete connector Caddie is built and tested against; the analytics-skill side is proven with a minimal example skill, not a specific organization's production query logic.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ Caddie core (this repo)                                              │
│  - /caddie-install, /caddie-update,                                  │
│    /caddie-ask, /caddie-load, /caddie-list                           │
│  - uv/Python bootstrap                                               │
│  - Marimo notebook lifecycle (create/execute/load)                   │
│  - shared Plotly charting template                                   │
│  - config file + manifest loading                                    │
└─────────┬──────────────────────┬────────────────────────┬────────────┘
          │                      │                        │
    invoked by name        loads by name            loads by name
          │                      │                        │
┌─────────▼──────────┐ ┌─────────▼───────────┐ ┌──────────▼─────────────┐
│ Analytics skill     │ │ Data connector      │ │ Context/RAG plugin     │
│ (Claude Code skill, │ │ (in-process Python  │ │ (deferred — see below, │
│  invoked via Skill  │ │  interface)         │ │  likely an MCP server) │
│  tool)              │ │ e.g. "databricks"   │ │ e.g. local MCP RAG     │
│ - turns a question  │ │ - opens a session   │ │ - search prior analyses│
│   into SQL/Python   │ │ - runs a query,     │ │ - index completed      │
│   for a code cell   │ │   returns a         │ │   notebooks on run     │
│                     │ │   DataFrame         │ │                        │
└─────────────────────┘ └─────────────────────┘ └─────────────────────────┘
```

Caddie core never contains org-specific logic (table names, metric definitions, business rules) or backend-specific query code. Those live entirely inside the plugins. The three plugin types are not architecturally identical: the connector is an in-process Python interface Caddie's own code calls directly; the analytics skill is a Claude Code skill invoked the normal way skills are invoked, not a Python API; the context plugin is deferred but expected to be an MCP server connection, a third distinct integration shape.

## Configuration

- `caddie.yaml` is a **local, user-level config file** at `~/.caddie/caddie.yaml` the user (or `/caddie-install`, on their behalf) authors it, and it specifies:
  - `skills`: a list of one or more analytics skill names to make available (Claude Code skills — see `skill_repo` below for where they come from). A single-skill setup is just a one-item list; nothing in the config format singles out "one skill" as the default case.
  - `skill_repo`: the org's skill repo (URL or local path) to clone, which may contain one or more skills; `skills` names which of the ones in it Caddie should actually use.
  - `connector`: the name of the data connector plugin to use (e.g. `databricks`).
  - Connector-specific settings needed at install/connect time (e.g. for Databricks: workspace `host` URL, CLI profile name, serverless vs. cluster mode). `host` in particular has to come from somewhere — see `caddie.default.yaml` below, since it's not something Caddie core or a fresh user can know on its own.
  - `context` (optional, deferred — see Context/RAG plugin below): the name of a context plugin to load, if the user has one configured.
- `/caddie-install` prompts for (or accepts as flags) the values above the first time it runs, and writes them to `~/.caddie/caddie.yaml`. On subsequent runs of any command, that file is read rather than re-prompting.
- There is a single config file, not a separate generated cache: `/caddie-install` writes username, notebooks root path (default or override), and the local path where `skill_repo` was cloned directly into `~/.caddie/caddie.yaml`, alongside the fields the user supplied. Every command reads this one file. (An earlier draft of this spec had a separate `~/.caddie/config.json` for "resolved" state; that added a second file without a real reason — nearly everything in it either duplicated `caddie.yaml` or was cheaply derivable from it, so it was dropped.)
- Editing `~/.caddie/caddie.yaml` directly (to point at a different skill, connector, or repo) and re-running `/caddie-update` is how a user switches setups — no org-side file, and nothing in Caddie core, needs to change.
- Because `caddie.yaml` is both hand-edited and machine-written (`/caddie-install` fills in the install-derived fields), writes must preserve the user's existing formatting/comments rather than blindly overwriting the file — a plain YAML round-trip library, not a naive full rewrite.

### `caddie.default.yaml`: org-provided install defaults

`caddie.yaml` being local and user-authored (per the decision above) doesn't mean every new user starts from a blank slate. When an organization sets up Caddie for itself — by forking the skill repo template (what was previously called `eureka`) — it can include a `caddie.default.yaml` in that repo alongside its skills. This file carries the org's known-good starting values: `skills`, `connector`, and connector settings including things like the Databricks `host` URL that a new user has no way to guess.

- `/caddie-install` clones `skill_repo` first (as it already does), then checks for a `caddie.default.yaml` at its root.
- If found, install shows each default value and prompts the user to accept it or supply their own (e.g. "Databricks host: `https://coursera-data-dev.cloud.databricks.com` — press enter to accept, or type a different value"), field by field. Accepting requires no typing.
- If `caddie.default.yaml` is absent, install falls back to plain prompts with no suggested value, as already specified.
- `caddie.default.yaml` is never read again after install — it seeds the one-time creation of the user's `~/.caddie/caddie.yaml` and has no further role. Editing it later only affects the next fresh install (e.g. a new teammate joining), not existing users; `/caddie-update` never re-reads it.
- `caddie.default.yaml` is checked into the skill repo (it contains no secrets — a workspace URL and connector name, not credentials) and is a normal part of what a "fork this repo for your org" setup step produces.

## Data connector plugin interface

Every connector plugin implements a small, backend-agnostic interface:

- `authenticate()` — perform whatever one-time or per-session auth the backend needs (OAuth, key pair, etc.); must never accept a pasted long-lived secret as the primary path.
- `get_session()` — return a live session/handle a notebook cell can query against.
- `execute(query)` — run a query and return a DataFrame-like result, for install-time verification and for `/caddie-load`-style diffing.
- `describe()` — return enough metadata (backend name, profile/account, connection mode) for the install summary and error messages.

### First implementation: Databricks

- Uses Spark Connect, not the SQL connector:
  ```python
  spark = DatabricksSession.builder.profile("<profile-name>").serverless(True).getOrCreate()
  ```
- Requires the `databricks-connect` Python package and a Databricks CLI profile (name comes from the user's `caddie.yaml`, e.g. `coursera-data-dev`).
- Auth is OAuth browser login. If the named profile doesn't already exist in `~/.databrickscfg`, `authenticate()` creates it with `databricks auth login --host <host> --profile <profile-name>`, where `host` comes from `caddie.yaml` (itself seeded from `caddie.default.yaml` at install time, per Configuration above — this is the one thing a connector needs that neither Caddie core nor a brand-new user can supply on their own). If the profile already exists, `--host` isn't needed. Never a personal access token.

### Future implementations (not built in this pass, interface must accommodate them)

- Snowflake (key-pair or SSO auth, `snowflake-connector-python` or Snowpark).
- PostgreSQL (standard connection string / SSO-backed proxy, `psycopg`).

## Analytics skill interface

An analytics skill is not a Python function Caddie calls into — it's a **Claude Code skill** (a markdown skill definition, invoked via the Skill tool). `caddie.yaml` may name more than one (see `skills` under Configuration above); when it does, Caddie doesn't pick one programmatically — the normal Claude Code skill-selection mechanism applies, the same way it would if all of a user's configured skills were simply available to the assistant. Each skill's own description/trigger is what makes it a good or bad match for a given question, exactly as with any other Claude Code skill; Caddie is not in the business of scoring or ranking them itself. If only one skill is configured, there's nothing to select between and it's invoked directly.

Whichever skill is invoked is given:

- the question being asked
- the active connector's live session/handle (so the skill's generated code queries through the connector, not through logic the skill invents itself)

The skill's own instructions are responsible for producing the markdown restating the question and the code (SQL string, or Python using the connector's session) that becomes the notebook's code cell. Whatever org-specific context the skill needs (metric definitions, table docs) lives inside that skill's own instructions/resources — Caddie core never inspects or depends on it, and never contains a Python interface that skill authors must implement.

Skill authorship (how a specific org writes a good analytics skill) is out of scope for Caddie itself — Caddie only needs to prove it can invoke *a* skill by name, hand it a question and a connector session, and correctly parse its output into notebook cells; and, when multiple are configured, that the right one is reachable and none of the others interfere. Validation of this interface should use minimal example skills built for testing (at least two, to prove selection works), not a specific organization's production analytics logic — that keeps Caddie core decoupled from any one org's implementation details.

## Context/RAG plugin interface (deferred)

**Status: explicitly deferred — not built in this pass.** Recorded now so the architecture and `/caddie-ask` flow accommodate it later without rework, and so it isn't accidentally designed as an afterthought.

The intent: when a `context` plugin is configured for an org, `/caddie-ask` should be able to search prior analyses for similar approaches before generating a new one, and completed notebooks should be indexed into that same store so future questions benefit from past work — turning one-off analyses into a growing, searchable corpus instead of a pile of disconnected notebook files.

Planned interface shape (to be finalized when this is actually built):

- `search(question)` — return prior analyses (notebook excerpts, summaries, or metadata) relevant to a new question, for the skill or `/caddie-ask` itself to consider before generating a new notebook.
- `index(notebook_path, question, summary)` — called after a notebook successfully executes, to add that completed analysis to the context store.

The first concrete implementation is expected to be a local MCP server backing a RAG system the user already runs, connected to Caddie as an MCP server rather than a Python import — meaning this plugin type may look different at the integration layer than the connector plugin (which is in-process Python), and that difference needs to be resolved as part of building it, not assumed away now.

When absent from the user's `caddie.yaml`, `/caddie-ask` behaves exactly as it does today — no context search, no indexing. This must remain a strict no-op when unconfigured, not a degraded mode.

## Notebook & charting stack

- Notebooks are [Marimo](https://marimo.io) notebooks (`.py` files, not `.ipynb`), not classic Jupyter. Marimo notebooks are pure Python, git-diffable, and reactive (cells re-run automatically when upstream cells change).
- Charting library: [Plotly](https://plotly.com/python/) via `plotly.express`, rendered as Marimo's native interactive chart element. Plotly is chosen because it renders natively inside Marimo, supports templates (`plotly.io.templates`) for consistent styling across notebooks, and produces interactive charts (zoom, hover, filter) that hold up when a notebook is handed to a teammate.
- A shared Plotly template (colors, fonts, layout defaults) lives in Caddie core and is imported by every generated notebook regardless of org, so all `/caddie-ask` output looks consistent without each notebook redefining style. Users may override specific template values (e.g. brand colors) via their `caddie.yaml`, but the base template is core, not per-org.

## Background

Today, ad hoc data-querying skills run a query and return a result inline in chat. Nothing persists: a follow-up question starts from scratch, and there is no artifact a user can open, re-run, or hand to a teammate. This spec introduces five commands that together create, maintain, and surface that artifact — implemented once in Caddie core, reused by any org that plugs in a skill and a connector.

## Commands

### Implementation shape: script-backed, not skill-generated

`/caddie-install`, `/caddie-update`, and `/caddie-list` are deterministic operations — the same steps (or the same filesystem query), every time, with no judgment call to make. They are implemented as a real Python CLI (e.g. `caddie install`, `caddie update`, `caddie list`, installed via the Caddie core package) that does the actual work: checking/installing tools, cloning repos, writing config, running verification, or globbing the notebooks folder. The Claude Code skill behind each invokes that script and relays/interprets its output — it does not generate shell commands or hand-roll a directory listing live. This makes these three testable against fixed definitions of done, reliably idempotent/deterministic, and reviewable as ordinary code, rather than behavior that can drift between runs. `/caddie-ask` and `/caddie-load` are different in kind — `/caddie-ask` calls the connector interface and invokes an analytics skill dynamically per question, and `/caddie-load` re-establishes context and re-runs an existing notebook — neither is script-backed in this same sense, though the notebook-lifecycle mechanics they share (build/execute a Marimo notebook) are still ordinary Caddie-core code, not commands improvised per run.

### `/caddie-install`

One-time laptop bootstrap, executed by running the install script described above.

- Check for `uv`; install via the official installer if missing.
- Install a pinned Python version via `uv python install`.
- If `~/.caddie/caddie.yaml` already exists, read it directly with no re-prompting and skip straight to the tool/connector setup below.
- Otherwise, prompt for (or accept as a flag) `skill_repo` first, then clone it.
- Check for `caddie.default.yaml` at the root of the cloned `skill_repo`. If present, prompt for `skills`, `connector`, and connector settings with each field pre-filled from that file (accept-or-override, per `caddie.default.yaml` above); if absent, prompt for the same fields with no suggested value.
- Write the resulting `skill_repo`, `skills`, `connector`, and connector settings into a new `~/.caddie/caddie.yaml`.
- Install whatever the chosen connector needs (e.g. Databricks CLI + `databricks-connect` for the `databricks` connector) — connector-specific, driven by the plugin, not hardcoded in core.
- Run the connector's `authenticate()` step (e.g. `databricks auth login --host <host> --profile <profile-name>` for Databricks, `host` from the `caddie.yaml` just written). Never prompt for or accept a pasted personal access token or other long-lived secret as the primary path.
- Determine the user's identity (from `git config user.email`, falling back to OS user) and resolve the notebooks root: use the user's override if one was given, otherwise the default (see Storage below); create that folder.
- Write username, resolved notebooks root path, and the local skill repo path into `~/.caddie/caddie.yaml`, alongside the fields already there.
- Verify the setup: identity check appropriate to the connector (e.g. `databricks current-user me`), then a live check via the connector's `execute()` on a trivial query.
- Print a clear pass/fail summary for each step.

### `/caddie-update`

Idempotent refresh of the environment, not the data, executed by the same install/update script (a separate `caddie update` entry point).

- Re-check `uv` and connector-specific CLI versions; upgrade if out of date.
- Re-read `~/.caddie/caddie.yaml` in case the user edited it (e.g. switched skill, connector, or `skill_repo`) since the last run, and re-clone/re-point at `skill_repo` if it changed.
- `git pull` the skill repo (picks up skill changes).
- Re-sync Python dependencies (`uv pip sync` / `uv sync`).
- Leave existing auth and notebooks untouched unless the connector's auth check fails, in which case re-run `authenticate()`.

### `/caddie-ask "<question>"`

The enforced entry point for analysis. Must always produce or extend a notebook — never answer a data question with just an inline chat result, and never stop at a single query's shape (row/column count) in place of a real answer.

- `/caddie-ask` is required to start a project (the first question in a new analysis). It is not required again for every message after that.
- A follow-up data question later in the same conversation is treated as an implicit continuation of the active project — a new episode in that project (see Episodes below) — without the user needing to retype `/caddie-ask`. This is a deliberate anti-bypass rule: if follow-ups after the first `/caddie-ask` were answered as plain chat, the "never answer inline" guarantee would only hold for the first question in a session and would quietly erode after that.
- Judging "is this message a continuation of the active analysis" is a judgment call, not a deterministic trigger like the slash command itself — a plain clarifying question about the existing notebook, a follow-up that changes the underlying question, and a clearly unrelated new topic should all be told apart. When it's ambiguous whether a message continues the active project or starts a new one, ask rather than guess.
- Look up the user's config from `~/.caddie/caddie.yaml`; if missing, instruct the user to run `/caddie-install` first.
- Determine the target project: a new question with no active project in this conversation creates a new project folder with a slug derived from the question; a continuation of an existing project adds a new episode to it instead.
- If a `context` plugin is configured (deferred — see Context/RAG plugin interface above; no-op when absent), search it for similar prior analyses before generating, and surface anything relevant to the user or the skill.

**Episodes.** One `/caddie-ask` question is an episode, not a single query — the point is to actually answer the question, which usually takes more than one step:

1. **Clarify.** Before planning, resolve anything genuinely ambiguous about the question — time range, a segment/filter it implies, granularity for a time series, and, where it isn't obvious, what decision the answer needs to support. Ask the user rather than guess; skip asking when the question is already fully specified.
2. **Plan.** Invoke the configured analytics skill (via the Skill tool, from the `skills` list in `caddie.yaml`) for org-specific grounding — table/column names, metric definitions, an example query — as input to a stated plan: the decision being supported, the scope, and the anticipated approach. The plan is written into the notebook as its own cell *before any query runs*, and can be revised in place later if execution reveals it was wrong.
3. **Execute.** Run one step at a time (a query, or occasionally a chart when a chart is genuinely the clearest way to convey a result — never as a default). After each step, decide whether to continue, revise the plan, add a chart, or conclude, bounded by a small iteration cap to prevent an unbounded loop. Each step is executed for real against the connector's live session, and a bounded, adaptive preview of the actual result (not just shape) is what the loop reasons from — the notebook's own cell always holds the full, uncapped result regardless of preview size. Pushing aggregation/filtering into the query is how this scales to real data volumes; a wider preview is an occasional exception, not the default way to "see more data." If answering genuinely requires judging many individual rows rather than a query-computed aggregate, that must be stated plainly in the answer (sample size, an honest caveat), not implied away.
4. **Answer.** Conclude with a real natural-language answer — a number, a short table, whatever the question needs — written into the notebook as its own cell, then render the whole notebook to a static, fully-executed file the user can open with one click, no further action needed.
- If a `context` plugin is configured, index the completed episode (question, summary, path) into it once it concludes (deferred — no-op when absent).
- Report back in chat: the answer text, the click-to-open rendered link, and (if it happened) a note that the plan was revised — never the full raw output.

### `/caddie-load <project>`

Bring an existing notebook back into context — the general-purpose way to resume work on a project, including in a brand-new conversation/session that never ran `/caddie-ask` for it.

- Locate the named project under the user's notebooks folder.
- Load the notebook's existing episodes (question, plan, steps, answer) into the conversation's context, so the user can immediately ask follow-up questions against it the same way they could mid-session with `/caddie-ask` (same implicit-continuation behavior, same anti-bypass rule: once loaded, treat this as the active project for follow-ups — a plain follow-up becomes a new episode).
- By default, re-execute every step in every episode, in order, against live data, via the connector recorded for that project (a notebook always re-runs against the same connector it was created with) — loading a notebook implies wanting current data, not a stale snapshot. Plan and answer cells are reported, not re-executed.
- Report what changed in the output (e.g. row counts, key metric deltas) compared to the previous run, where feasible, and re-render the click-to-open file so its link reflects the latest data.
- Fail clearly (not silently) if a step no longer runs (e.g. schema changes, auth expired, connector unreachable) — loading context still succeeds in this case (the user can see and discuss the existing notebook), only that step's re-run (and the render, if it depends on that step) fails.

### `/caddie-list [pattern]`

Find existing projects under the user's notebooks folder — the discovery step before `/caddie-load <project>`, for when the user doesn't remember (or want to type) the exact project slug. Executed by the same kind of script as install/update (a `caddie list` entry point) — plain filesystem globbing, not something worth generating live.

- With no argument, lists projects for the current user, most-recently-modified first (based on the notebook file's mtime), so `/caddie-list` alone answers "what have I been working on."
- `--recent [N]` limits the listing to the N most recently modified projects (default N if omitted, e.g. 10).
- A `pattern` argument accepts `ls`-style wildcards (`*`, `?`, `[...]`) matched against project slugs, e.g. `/caddie-list "revenue-*"`, so the user can narrow by topic without recalling the full name.
- Read-only: never creates, modifies, deletes, or executes a notebook. Purely a discovery/lookup command.
- Each result shows at minimum the project slug and last-modified time, so the output can be handed directly to `/caddie-load <project>`.
- An empty result set (no projects, or none matching the pattern) is reported plainly, not as an error.

## Storage

- Default notebooks root is `~/caddie/notebooks/<username>/<project-slug>/notebook.py`, entirely **local to the laptop** — never committed to any org's repo.
- The notebooks root is user-configurable: `/caddie-install` accepts an optional override (flag or prompt) for the root path, and the resolved value is written to `~/.caddie/caddie.yaml`. If the user gives no override, the default above is used. This is a per-user, per-machine setting — consistent with `caddie.yaml` itself being local and user-level, two people pointed at the same `skill_repo` each have their own `caddie.yaml` and can keep notebooks somewhere different on their own laptops.
- `~/.caddie/caddie.yaml` (local, not in git) is the single source of truth other commands read to find the user's folder and active plugins, avoiding repeated prompts.

## Non-goals / open questions

- No decision yet on how `/caddie-ask` and `/caddie-load` invoke Marimo for non-interactive execution (`marimo run` vs a scripted `marimo export`/CLI call) — to be resolved during implementation.
- Building additional connector plugins is out of scope for this pass — only the interface needs to accommodate them.
- Building the Context/RAG plugin (including wiring up the user's local MCP RAG server) is explicitly deferred — only the interface shape and the `/caddie-ask` no-op hooks need to exist in this pass.  We already have local-rag we can leverage.
- Whether the context plugin integrates as an MCP server connection versus an in-process Python plugin like the connector type is unresolved and needs a decision before it's built.