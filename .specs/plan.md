# Caddie — Implementation Plan

Sequential steps derived from [requirements.md](requirements.md). Mac only for this pass (Windows is a later phase). Order builds the generic harness and plugin interfaces first, then plugs in a minimal test skill and Databricks (connector) as the first concrete pair, then wires up the five commands. The test skill is a throwaway example built to validate the invocation path — it is not any specific organization's production analytics logic, and none of this plan depends on or references one. Each step ends with a commit and push to GitHub before starting the next — do not begin step N+1 with step N's work uncommitted.

---

## Step 1 — Caddie core repo scaffold

Set up the Caddie core repo structure: `pyproject.toml` managed by `uv`, pinned Python version, and the core dependencies (`marimo`, `plotly`). No connector or skill dependencies yet — those belong to plugins.

**Definition of done:**
- `uv sync` completes cleanly from a fresh clone.
- `uv run python -c "import marimo, plotly"` exits 0.
- `uv run python --version` matches the pinned version in `pyproject.toml`.
- No connector-specific or org-specific package or code exists anywhere in the repo at this point.

**Commit:** "Scaffold Caddie core repo with uv, Marimo, Plotly"

---

## Step 2 — Shared Plotly template (core)

Add the single shared Plotly template (colors, fonts, layout defaults) as a Caddie-core module, org-agnostic.

**Definition of done:**
- A module (e.g. `caddie/charting/template.py`) registers a named template via `plotly.io.templates`.
- A throwaway script that builds a `plotly.express` chart with the template applied renders without error and visibly uses the custom styling (checked manually by opening the output HTML/image).
- The module has no reference to any org name, table name, or backend.

**Commit:** "Add shared Plotly template to Caddie core"

---

## Step 3 — Connector plugin interface (abstract)

Define the data connector interface (`authenticate()`, `get_session()`, `execute(query)`, `describe()`) as an abstract base/protocol in Caddie core, plus a plugin-loading mechanism that resolves a connector by name.

**Definition of done:**
- A minimal fake/in-memory connector implementing the interface can be loaded by name (e.g. `load_connector("fake")`) and its four methods called successfully from a test script.
- Attempting to load a connector name that doesn't exist raises a clear, specific error (not a generic import traceback).
- The interface file contains no Databricks-specific types or imports.

**Commit:** "Add connector plugin interface and loader to Caddie core"

---

## Step 4 — Skill invocation mechanism (abstract)

An analytics skill is a Claude Code skill (invoked via the Skill tool), not a Python interface — there's nothing to define as an abstract base class here. `caddie.yaml`'s `skills` field can name more than one; Caddie's invocation path doesn't rank or choose between them itself (that's ordinary Claude Code skill selection, based on each skill's own description), it just needs to confirm each named skill is actually invokable and hand the chosen one the question plus the active connector's session, then parse its output into a markdown string and a code string.

**Definition of done:**
- A minimal test skill (a real, trivial Claude Code skill built purely for this validation, that always returns a hardcoded `SELECT 1` plus fixed markdown) can be invoked by name through Caddie's invocation path, using the fake connector from Step 3, and the output is correctly split into a markdown string and a code string.
- Given `skills: [test-skill-a, test-skill-b]`, Caddie's invocation path confirms both are present/loadable at startup (e.g. as part of `caddie install`'s verification), without needing to pick one itself.
- Attempting to invoke a skill name that doesn't exist/isn't installed raises a clear, specific error, not a silent failure or a hallucinated response.
- Caddie core's invocation code contains no org-specific or connector-specific logic — it only knows how to invoke *a* skill by name and parse its output shape.

**Commit:** "Add analytics skill invocation path to Caddie core"

---

## Step 5 — Local config loading (`caddie.yaml`)

Implement reading/writing the user's local `~/.caddie/caddie.yaml` — the single config file (`skills` list, `skill_repo`, connector name, connector settings, and the install-derived fields: notebooks root, local skill repo clone path). No separate generated cache file; every command reads and, where relevant, writes this one file directly, using a YAML round-trip library so hand-added comments/formatting survive a machine write.

**Definition of done:**
- Given a sample `~/.caddie/caddie.yaml` with `skills: [test-skill]`, `skill_repo: <test-fixture-path>`, and `connector: fake`, a loader function returns a structured object with all fields present, with `skills` as a list even though it has one entry.
- Given a sample with `skills: [test-skill-a, test-skill-b]`, the loader returns both names — the loader itself does no selection, it just parses the list.
- A round-trip test — load the file, write back an updated field (e.g. `notebooks_root`), reload — preserves a hand-added comment elsewhere in the file rather than stripping it.
- Malformed or missing required `caddie.yaml` fields produce a clear validation error, not a KeyError/stack trace.
- Editing `caddie.yaml` by hand (e.g. changing `connector`) and re-running the loader picks up the change immediately — there is nothing else to invalidate or re-sync.

**Commit:** "Implement local caddie.yaml loading and round-trip-safe read/write"

---

## Step 6 — Databricks connector plugin

Implement the real Databricks connector against the interface from Step 3: Spark Connect / `DatabricksSession`, OAuth login, live query execution.

**Definition of done:**
- `authenticate()` accepts a `host` setting and, when the named profile doesn't yet exist, runs `databricks auth login --host <host> --profile <profile-name>`; completing the browser OAuth flow leaves `databricks current-user me --profile <profile-name>` succeeding.
- Calling `authenticate()` again when the profile already exists succeeds without requiring `host` to be passed.
- `get_session()` returns a working session via `DatabricksSession.builder.profile(<profile-name>).serverless(True).getOrCreate()`.
- `execute("SELECT 1")` returns a result via that session.
- Inspecting `~/.databrickscfg` after `authenticate()` shows no `token` field (OAuth only, never a PAT).

**Commit:** "Implement Databricks connector plugin"

---

## Step 7 — Test skill against the real Databricks connector

Prove Caddie's Step 4 invocation path drives a real backend correctly by pairing the minimal test skill with the real Databricks connector from Step 6 (still not any organization's production analytics logic — this is validating plumbing, not shipping a real skill).

**Definition of done:**
- Invoking the test skill through Caddie's invocation path with a real question returns a markdown string containing the literal question and a code string that is valid SQL/PySpark referencing the Databricks connector's session.
- Running the returned code string directly against a live Databricks session (manually, outside a notebook) executes without syntax errors and returns a result.
- With a second test skill added (`skills: [test-skill-a, test-skill-b]`, each with a distinct, clearly-worded description/trigger), asking a question matching skill B's description results in skill B being invoked, not A — proving multi-skill selection works via ordinary Claude Code skill matching, with no special-casing needed in Caddie core.
- The test skills' definitions live outside Caddie core (their own small test-fixture repo or directory), and Caddie core contains zero copies or reimplementations of their logic.

**Commit:** "Validate skill invocation path against real Databricks connector, including multi-skill selection"

---

## Step 8 — `caddie install` script: tool bootstrap, `caddie.default.yaml`, and caddie.yaml resolution

Per requirements.md, `/caddie-install` is script-backed, not skill-generated: build a real Python CLI entry point (`caddie install`) that the skill invokes. This step implements the first half: `uv`/Python checks, cloning `skill_repo`, reading an optional `caddie.default.yaml` at its root to seed prompt defaults, and writing (or reading, if it already exists) the user's local `~/.caddie/caddie.yaml`. No shell commands are improvised by the skill at any point — the skill only calls this script and relays its output.

**Definition of done:**
- Running `caddie install --skill-repo <test-fixture-path-with-defaults>` against a test-fixture repo that contains a `caddie.default.yaml` (with `skills`, `connector`, and a fake `host` setting) — fresh machine, no existing `~/.caddie/caddie.yaml` — prompts for each field pre-filled with the default value, and pressing enter on all of them writes a `caddie.yaml` matching the defaults exactly.
- Running the same command against a test-fixture repo with no `caddie.default.yaml` prompts for the same fields with no suggested value, and requires the user to type each one.
- Overriding one prompted value (e.g. typing a different `connector`) results in that value, not the default, ending up in `caddie.yaml`.
- Running `caddie install --skills test-skill-a,test-skill-b --skill-repo <test-fixture-path> --connector databricks` (flags, no prompting) writes `caddie.yaml` with `skills` as a list of both names.
- Running `caddie install` again with no flags, `caddie.yaml` already present, reads it as-is and does not re-prompt, re-read `caddie.default.yaml`, or overwrite it; does not re-clone `skill_repo` if already present (idempotent).
- Running on a machine missing `uv` installs it; running again when present is a no-op.
- The `/caddie-install` skill definition itself contains no shell/install commands — only logic to invoke `caddie install` and interpret its output.

**Commit:** "Implement caddie install script: caddie.default.yaml-seeded prompts and caddie.yaml resolution"

---

## Step 9 — `caddie install` script: connector setup, identity, finishing `caddie.yaml`

Finish the install script: run the resolved connector's install/auth steps, resolve user identity, resolve the notebooks root (default or user override), create that folder, write the install-derived fields into `~/.caddie/caddie.yaml`, and verify end-to-end.

**Definition of done:**
- Running `caddie install` directly from a clean state against the test-fixture config, with no override given, ends with a printed pass/fail summary where every line is "pass," including a live Databricks query check — runnable and verifiable with no Claude Code session involved.
- With no existing Databricks CLI profile of the configured name, `authenticate()` runs `databricks auth login --host <host> --profile <profile-name>` using the `host` value resolved from `caddie.yaml`; with the profile already present, it omits `--host`.
- `~/caddie/notebooks/<username>/` exists after running with no override, where `<username>` is derived from `git config user.email`.
- Running `caddie install --notebooks-root <custom-path>` creates `<custom-path>/<username>/` instead, and `~/.caddie/caddie.yaml` records that custom path.
- `~/.caddie/caddie.yaml` contains username, skill/connector names, connector settings (including `host`), resolved notebooks root, and the local skill repo clone path, all in the one file.
- Invoking `/caddie-install` end-to-end through Claude Code produces identical results to running `caddie install` directly.

**Commit:** "Complete caddie install script: connector setup, identity, config file"

---

## Step 10 — `caddie update` script

Implement the idempotent refresh command as its own script entry point (`caddie update`), connector-agnostic, invoked by the `/caddie-update` skill the same way install is.

**Definition of done:**
- Running `caddie update` directly on an already-current setup makes no changes and reports success.
- After manually editing a dependency version behind, running `caddie update` brings it back in sync with `pyproject.toml`.
- Deliberately expiring/removing the Databricks auth profile, then running `caddie update`, triggers the connector's `authenticate()` re-run; existing notebooks and their contents are untouched.
- The `/caddie-update` skill definition contains no shell/install commands — only logic to invoke `caddie update` and interpret its output.

**Commit:** "Implement caddie update script with idempotent environment refresh"

---

## Step 11 — Marimo notebook generation via skill invocation (no execution yet)

Implement the notebook-building half of `/caddie-ask`: invoke the active skill (via the Step 4/7 invocation path), build the Marimo notebook file with the required cell structure, without running it.

**Definition of done:**
- Running the command with a novel question creates `~/caddie/notebooks/<username>/<slug>/notebook.py` as a valid Marimo notebook (opens successfully in `marimo edit`).
- The notebook contains a markdown cell with the literal question text, a code cell with the code returned by invoking the configured skill, and a designated output cell.
- Running the command again with an existing project name/continuation appends a new cell group to the same file instead of creating a second notebook.

**Commit:** "Generate Marimo notebooks from skill invocation output"

---

## Step 12 — `/caddie-ask`: execution and chat report-back

Wire up non-interactive execution of the generated notebook against the connector recorded in config, and the chat summary response.

**Definition of done:**
- After running `/caddie-ask` with a real question, the notebook's output cell contains actual Databricks query results (not placeholder/empty state) when reopened in `marimo edit`.
- The chat response includes the correct absolute file path to the notebook and a summary that does not include full raw row-level output.
- Asking a question that produces a deliberately broken query (e.g. a bad table name) surfaces a clear error in chat rather than a silently empty notebook.

**Commit:** "Execute generated notebooks via connector and report results in chat"

---

## Step 13 — `/caddie-load`

Implement bringing an existing notebook back into context (including in a fresh conversation that never ran `/caddie-ask` for it), re-executing it by default against the same connector it was created with, and the diff-style report.

**Definition of done:**
- Running `/caddie-load <project>` in a brand-new conversation loads the notebook's existing cells into context and, without further prompting, re-executes all cells and updates the output cell(s) in place.
- After loading, a plain follow-up chat message (not a `/caddie-ask` re-invocation) is treated as a continuation of that project, appending to the same notebook — same behavior as an implicit `/caddie-ask` follow-up.
- The chat report includes at least one concrete comparison to the previous run (e.g. row count delta) when the underlying data has changed between runs.
- Running `/caddie-load` on a notebook whose query now references a dropped/renamed column still successfully loads the notebook into context, but reports a clear, specific error for the failed re-run (not a stack trace dump, not a silent no-op).

**Commit:** "Implement /caddie-load with context loading, default re-run, and change reporting"

---

## Step 14 — `caddie list` script

Implement the `caddie list` script entry point: glob the user's notebooks folder for project directories, support `--recent [N]` and an `ls`-style wildcard pattern argument, invoked by the `/caddie-list` skill the same way install/update/list are.

**Definition of done:**
- Running `caddie list` directly with several existing test projects (varying mtimes) prints them most-recently-modified first.
- Running `caddie list --recent 2` prints only the 2 most recently modified projects.
- Running `caddie list "revenue-*"` against a mix of matching and non-matching project slugs prints only the matches.
- Running `caddie list` against an empty notebooks folder prints a plain "no projects found" message, not an error or stack trace.
- The command never touches (creates, modifies, executes) any notebook file — verified by checksums/mtimes on the notebook files being unchanged before and after running it.
- The `/caddie-list` skill definition contains no filesystem-walking logic of its own — only logic to invoke `caddie list` and relay its output.

**Commit:** "Implement caddie list script for project discovery"

---

## Step 15 — End-to-end dry run

No new features — a full walkthrough on a clean machine (or clean state) using the test skill/Databricks pair, to confirm the whole harness + plugin architecture works together, plus a review of what got written to git in both the Caddie core repo and the test-fixture org repo.

**Definition of done:**
- From a machine with none of the tooling installed, running `/caddie-install` (pointed at the test-fixture repo) → `/caddie-ask "<question>"` → `/caddie-list` → `/caddie-load <project>` in order succeeds with no manual intervention beyond the OAuth browser step, and the project name printed by `/caddie-list` is the same one `/caddie-load` successfully loads.
- `git status` in both the Caddie core repo and the test-fixture repo after the full walkthrough shows no notebook files, no `caddie.yaml`, and nothing under `~/caddie/notebooks/` staged or tracked.
- Manual review confirms no organization-specific or connector-specific code exists anywhere in the Caddie core repo.

**Commit:** "Verify end-to-end Caddie flow with test skill/Databricks plugins, confirm no org-specific code leaks into core"

---

## Step 16 — `/caddie-ask` episodes: clarify, plan, execute, adapt, answer

Steps 12–14 made `/caddie-ask` execute exactly one query and report its shape (row/column count). Real use against a live question ("what were NPLs last week") showed that isn't an answer — replaces the one-shot flow with an "episode" model: clarify ambiguous scope with the user, write an analysis plan into the notebook before pulling data, execute one step at a time against a real (adaptive, non-truncating-for-small-results) data preview, revise the plan in place if a step reveals it was wrong, add a chart only when one genuinely clarifies the result, conclude with a real natural-language answer, and render the whole notebook to a static file the user can open with one click. Breaking change to the cell-naming scheme and `.caddie_project.json`; no real users yet, so no migration.

**Definition of done:**
- `caddie notebook-start` creates a project/episode from a question with no execution; `caddie notebook-plan` requires an episode to exist and can be called again to overwrite the plan in place (not duplicate it).
- `caddie notebook-step` refuses to run before a plan exists for its episode; each call appends and executes one query or chart step, returning a real (row-count-aware, adaptively-capped) preview or a chart's figure description, never silently swallowing an error.
- `caddie notebook-answer` refuses before any step has run or after an episode already has an answer; on success it renders the whole notebook to a static HTML file via `marimo export html` and prints a `file://` link.
- `caddie notebook-rerun` re-executes every episode's steps in order (query and chart), reports per-step deltas against the previous run, reports each episode's current plan/answer without re-executing them, and re-renders the HTML file.
- `/caddie-ask` and `/caddie-load` SKILL.md instructions reflect the clarify → plan → execute (revisable) → answer loop, including the iteration cap and the rule that a wider preview is a deliberate exception, not the default way to see more data.

**Commit:** "Rebuild /caddie-ask as an iterative clarify/plan/execute/answer loop"

---

## Step 17 — Per-notebook sandboxed dependencies

Real use surfaced a dependency-management gap step 16 didn't cover: a notebook's own analysis code (a chart step needing `scikit-learn`, say) may need a package caddie core doesn't have, and installing it into caddie's own shared venv risks a conflict with caddie's own dependencies, or with what a different notebook needs. Gives every notebook its own PEP 723 dependency header and an isolated `uv`-managed environment for `/caddie-edit`, instead of one shared venv for everything.

**Definition of done:**
- `caddie notebook-start` writes a new notebook with a `# /// script` header declaring caddie (as a `file://` dependency on the running checkout) plus caddie's own runtime dependencies; `notebook-plan`/`notebook-step`/`notebook-answer` preserve that header unchanged on every subsequent write.
- `caddie notebook-edit` launches `marimo edit --sandbox`; opening a project's notebook this way starts successfully against an isolated environment — verified end-to-end: the sandboxed server serves the notebook with no import errors, using the `fake` connector — with no changes to caddie's own `.venv`.
- `caddie notebook-add-dependency --project <p> <package>` adds a package to one project's notebook header only (via `uv add --script`), verified to survive a subsequent builder write (e.g. `notebook-step`) and to be picked up the next time that notebook opens under `--sandbox`.
- caddie's own `pyproject.toml` and shared `.venv` are unchanged by adding a notebook dependency.
- `/caddie-edit`'s SKILL.md documents the sandbox and its first-launch cost; a new `/caddie-add-dependency` skill documents the new command; the README calls out per-notebook dependency isolation as part of what makes a Caddie notebook a genuinely reusable, reproducible artifact.

**Commit:** "Give each notebook its own sandboxed uv environment for dependencies"

---

## Step 18 — Portable notebooks (`/caddie-share`)

Step 17 isolated a notebook's *extra* dependencies from caddie's own venv, but the notebook still depends on `caddie` itself for its `setup` cell (config loading, connector resolution, chart template) — so it still only runs on a machine that can resolve caddie. Adds an on-demand way to produce a truly standalone copy for handing to someone without caddie: vendor the connector's and chart template's own source (both are caddie-import-free by design) into a rewritten, hidden `setup` cell, instantiated from the project's saved connector settings instead of `caddie.yaml`.

**Definition of done:**
- `caddie notebook-share --project <p>` writes `notebook.portable.py` alongside `notebook.py`, leaving `notebook.py` itself untouched.
- The portable file's `setup` cell is marked `hide_code` and contains no `caddie` import anywhere — verified by parsing its AST for any `caddie`/`caddie.*` import.
- The portable file's PEP 723 header omits `caddie` and `ruamel-yaml`; `uv export --script` on it resolves cleanly with no local path/editable entries.
- `uv run marimo export html --sandbox` on the portable file, in a machine state with no caddie checkout involved (a fresh `--isolated` uv environment), executes every cell without error and produces the same result as the working notebook.
- Regenerating (`/caddie-share` again) after connector settings change reflects the new settings; the working notebook is unaffected either way.
- A new `/caddie-share` skill documents the command and states plainly what "portable" does and doesn't cover (removes the `caddie` dependency; does not remove the data-backend/credential dependency; is a snapshot, not a live link).

**Commit:** "Add /caddie-share: standalone notebooks with no caddie dependency"

---

## Step 19 — Scope notebook dependency headers to the actual connector

Testing step 18 surfaced a real inefficiency: both the working notebook's and the portable notebook's dependency headers mirrored caddie's *entire* dependency list, so a `fake`-connector project's header (and its resolved sandbox) declared `databricks-connect` — a heavy package it will never import. Scopes both headers to what the project's actual connector needs.

**Definition of done:**
- `notebook/dependencies.py` computes a connector-agnostic base (marimo, plotly, and — for the working notebook only — ruamel-yaml) plus a small, explicit mapping of which dependencies belong only to a specific built-in connector (today: `databricks` → `databricks-connect`).
- `render_script_header(connector)` and `render_portable_script_header(connector)` take the project's connector name and only include that connector's own extra dependencies; verified for both `fake` (no `databricks-connect` in either header) and `databricks` (present in both).
- `caddie notebook-start` threads `config.connector` through to the header written for a brand-new notebook; an existing notebook's header is untouched (preserved as before).
- `caddie notebook-share` threads the project's saved connector (from `.caddie_project.json`) through to the portable header.
- caddie's own `pyproject.toml`, `uv sync`/`uv run` behavior, and install/update flow are unchanged — this is scoped entirely to header computation, not caddie's own packaging (see requirements.md for why splitting caddie's own dependencies into optional-dependency groups was considered and rejected).
- Verified end-to-end via the real CLI: a full `notebook-start` → `notebook-plan` → `notebook-step` → `notebook-answer` → `notebook-share` run against the `fake` connector produces a notebook and portable file with no `databricks-connect` in either header.

**Commit:** "Scope notebook dependency headers to the project's actual connector"

---

## Deferred — Future phase (not part of this build)

**Context/RAG plugin.** Per requirements.md, this is explicitly deferred and not one of the steps above — recorded here so it isn't lost, and so a future step is scoped before work starts on it:

- Define the context plugin interface (`search(question)`, `index(notebook_path, question, summary)`) in Caddie core, as a no-op when unconfigured.
- Resolve whether it integrates as an MCP server connection (matching the user's existing local MCP RAG solution) or as an in-process Python plugin like the connector type — this is an open design question, not a detail to fill in casually.
- Wire `/caddie-ask` to call `search()` before generating and `index()` after a successful run, gated entirely on whether `context` is present in the user's `caddie.yaml`.
- Definition of done for that future step, once scoped: asking a question that closely matches a previously indexed analysis surfaces that prior result before a new notebook is generated; running with no `context` configured produces byte-identical `/caddie-ask` behavior to today.

**Real-world skill/connector pairs beyond the test fixtures.** Which specific organization and analytics skill becomes the first production skill plugin is not decided in this plan — onboarding one is a separate future step once Caddie core is proven against the test skill.
