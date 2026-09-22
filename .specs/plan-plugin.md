# Caddie — Plugin Packaging Implementation Plan

Sequential steps derived from [requirements-plugin.md](requirements-plugin.md).
Order fixes the parts of the CLI that break under the plugin model first
(isolated, independently testable), then the config-yaml and identity
changes to `caddie install`/`caddie update`, then the plugin packaging
move itself (biggest, touches every skill/agent/output-style file), then
end-to-end verification. Each step ends with a commit before starting
the next — do not begin step N+1 with step N's work uncommitted.

---

## Step 1 — Stop relying on `caddie`'s own installed-package path

Fixes the root cause in ["Caddie's own root is no longer
knowable"](requirements-plugin.md#caddies-own-root-is-no-longer-knowable):
three places locate "the caddie project" by walking up from
`__file__`, which only resolves to something real from an editable git
checkout, not an installed tool.

- `install/marimo_pair.py`: `install_marimo_pair_skill`/
  `upgrade_marimo_pair_skill` install into `Path.home() / ".claude" /
  "skills"` instead of `CADDIE_CORE_ROOT / ".claude" / "skills"`.
- `update/command.py`: replace the `CADDIE_CORE_ROOT / "pyproject.toml"`
  check + `uv sync` with an unconditional `uv tool upgrade caddie`.
- `notebook/dependencies.py`: replace `caddie_root()` +
  `_caddie_project_metadata()` (parsing `pyproject.toml` off disk) with
  `importlib.metadata.version("caddie")` /
  `importlib.metadata.requires("caddie")`.
- Delete `CADDIE_CORE_ROOT` from `install/command.py` and
  `update/command.py` once nothing references it.

**Definition of done:**
- `grep -rn "CADDIE_CORE_ROOT\|caddie_root()" src/caddie/` returns
  nothing.
- With `caddie` installed via `uv tool install --editable .` from a
  *different* working directory than the checkout (proving no cwd or
  package-path assumption survives): `caddie install` installs
  marimo-pair into `~/.claude/skills/marimo-pair` (verified present),
  `caddie update` runs `uv tool upgrade caddie` successfully instead of
  failing to find `pyproject.toml`, and generating a notebook produces
  a PEP 723 header with the same dependency versions as before this
  change (verified by diffing the header against a notebook generated
  pre-change).
- Existing test-fixture flow (Step 6/7 in `plan.md`) still passes
  end-to-end with the `fake` and `databricks` connectors.

**Commit:** "Stop resolving caddie's own root from its installed package path"

---

## Step 2 — Drop skill-repo-internal `caddie.default.yaml` lookup

Per requirements-plugin.md's ["Config yaml
content"](requirements-plugin.md#config-yaml-content) decision: the
config yaml becomes the only source. Remove `load_defaults` and its
call site so `skill_repo` is never scanned for its own config file.

- Delete `install/defaults.py` (`load_defaults`).
- Remove the `defaults = load_defaults(skill_repo_path)` call and its
  use in `_resolve_fresh` (`install/command.py`).

**Definition of done:**
- `grep -rn "load_defaults\|caddie.default.yaml" src/caddie/` returns
  nothing.
- A test-fixture `skill_repo` that contains a `caddie.default.yaml` is
  resolved and its skills loaded normally, but its `caddie.default.yaml`
  content is never read or referenced (verified: deleting that file
  from the fixture changes nothing about `caddie install`'s behavior).

**Commit:** "Drop skill-repo-internal caddie.default.yaml lookup"

---

## Step 3 — Config yaml source for `caddie install` (local path or URL)

Implements ["Config yaml source (first
pass)"](requirements-plugin.md#config-yaml-source-first-pass): a new,
required input to `caddie install` — a local path or URL — replacing
the now-removed skill-repo-internal defaults as where prompt defaults
come from.

- New module (e.g. `install/org_config.py`): `load_org_config(source:
  str) -> dict`, handling a local/`~`-expanded path (same existence
  check as `resolve_skill_repo`'s local-candidate branch) or an
  `http(s)://` URL, fetched via stdlib `urllib.request` (already used
  elsewhere in the codebase, e.g. `notebook/edit.py` — no new
  dependency). No caching: re-running re-fetches.
- New `--config` flag on `caddie install` (`install/command.py`)
  carrying the source; if neither `--config` nor the individual flags
  (`--skill-repo`/`--skills`/`--connector`) are given, fail fast with a
  clear error instead of falling into `input()`.
- Delete `install/prompts.py` (`prompt_value`/`prompt_list`) and every
  call site — no remaining caller needs blind interactive prompting
  per the requirements doc's decision.

**Definition of done:**
- `caddie install --config <test-fixture-path>.yaml` (no other flags)
  loads that file's `skill_repo`/`skills`/`connector` and proposes them
  for confirmation, matching today's `caddie.default.yaml`-seeded
  prompt behavior exactly (same fixture content, same resulting
  `caddie.yaml`).
- `caddie install --config <url-to-same-fixture-content>` produces an
  identical `caddie.yaml` to the local-path case.
- `caddie install --skill-repo X --skills a,b --connector databricks`
  (no `--config`) still works via flags alone, unchanged from today.
- `caddie install` with none of `--config`/`--skill-repo`/`--skills`/
  `--connector` exits non-zero with a clear, specific error naming what
  to supply — not an `input()` prompt, not a stack trace.
- `grep -rn "prompt_value\|prompt_list" src/caddie/` returns nothing.

**Commit:** "Add config-yaml source to caddie install, drop blind interactive prompting"

---

## Step 4 — `/caddie:update` re-fetches the config yaml

Per the ["`/caddie:update` and the config
yaml"](requirements-plugin.md#caddieupdate-and-the-config-yaml)
decision: update re-resolves the org's config from the same source
(local/URL), re-proposing values for confirmation, alongside its
existing tooling/dependency/connector-auth refresh role.

- `update/command.py`: given the config source recorded from the last
  install (stored in `caddie.yaml` or passed via `--config`), re-run
  `load_org_config` and re-propose any changed `skill_repo`/`skills`/
  `connector` values the same way a fresh install does.

**Definition of done:**
- Editing the test-fixture config yaml's `connector` value, then
  running `caddie update` with no flags, surfaces the changed value
  for confirmation and updates `caddie.yaml` on accept.
- Running `caddie update` with the config yaml unchanged makes no
  config-related changes, only its existing tooling/dependency/auth
  refresh (regression check against `plan.md` Step 10's behavior).

**Commit:** "Re-fetch config yaml as part of caddie update"

---

## Step 5 — Drop identity/username resolution

Per ["Dropping identity
resolution"](requirements-plugin.md#dropping-identity-resolution): a
full requirement for this pass, not deferred.

- Delete `install/identity.py` (`resolve_username`).
- Remove the `username` field from `config/model.py`'s config object.
- Update the seven call sites doing `config.username or
  resolve_username()`: `caddie.notebook.start`, `.edit`, `.share`,
  `.add_dependency`, `.render`, `caddie.list.command`,
  `caddie.install.command`. Notebook paths become
  `~/caddie/notebooks/<project-slug>/notebook.py` (no `<username>`
  segment).

**Definition of done:**
- `grep -rn "resolve_username\|config.username" src/caddie/` returns
  nothing.
- A fresh `caddie install` run creates `~/caddie/notebooks/` directly
  (no per-user subfolder); an existing project's notebook resolves at
  `~/caddie/notebooks/<slug>/notebook.py` from every one of the seven
  call sites above, verified individually.
- `~/.caddie/caddie.yaml` written by install/update has no `username`
  key.

**Commit:** "Remove username/identity resolution from Caddie"

---

## Step 6 — Plugin scaffold: manifest, skill/agent renames, output-styles

The move itself, per ["Naming"](requirements-plugin.md#naming) and
["Plugin structure"](requirements-plugin.md#plugin-structure). Highest
blast radius of any step — touches every `SKILL.md` and every
cross-reference — so it comes after the behavior changes above are
already working, not mixed in with them.

- `.claude-plugin/plugin.json`: `name: "caddie"`, `description`,
  `version`.
- Move and rename `.claude/skills/caddie-*` → `skills/<short-name>`
  per the Naming table (`install`, `ask`, `list`, `load`, `edit`,
  `share`, `update`, `add-dependency`). Leave `marimo-pair`/
  `retro-marimo-pair` where they are — they're install-time-generated
  and already gitignored (`.gitignore` lines 217–224), not part of the
  plugin's static content.
- Move `.claude/agents/*` → `agents/`.
- Move `.claude/output-styles/*` → `output-styles/`.
- Update every `SKILL.md`'s own trigger text (e.g. `Trigger on
  "/caddie-install"` → `/caddie:install`) and every cross-reference in
  other `SKILL.md` files and the README to the `/caddie:<name>` form.
  README.md already has a draft of this in the working tree from this
  session — reconcile it against the actual moved files rather than
  redoing it from scratch.
- Remove the `caddie-install/SKILL.md` output-style workaround (asking
  in chat, writing `outputStyle` into `.claude/settings.local.json`)
  now that `output-styles/` ships natively.

**Definition of done:**
- `find . -path ./.git -prune -o -name SKILL.md -print` shows every
  skill under `skills/<short-name>/SKILL.md`, none under
  `.claude/skills/caddie-*`.
- `grep -rn "caddie-install\|caddie-ask\|caddie-list\|caddie-load\|caddie-edit\|caddie-share\|caddie-update\|caddie-add-dependency" --include=SKILL.md --include=README.md .`
  returns no hits in trigger/reference text (excluding this plan and
  requirements-plugin.md's own naming table, which documents the old
  names deliberately).
- `grep -rn "outputStyle" .claude/settings.local.json` workaround
  instructions no longer appear in `caddie-install`'s (now `install/`)
  `SKILL.md`.

**Commit:** "Package Caddie as a Claude Code plugin: manifest, renamed skills, agents, output-styles"

---

## Step 7 — Local dev verification (`--plugin-dir`)

No new features — confirm the packaged plugin actually works end to
end before considering distribution.

- `claude --plugin-dir ./caddie`, run each `/caddie:*` skill in turn
  against the test-fixture skill/connector pair from `plan.md`.

**Definition of done:**
- `/caddie:install --config <test-fixture-config>` → `/caddie:ask
  "<question>"` → `/caddie:list` → `/caddie:load <project>` succeeds in
  order with no manual intervention beyond the connector OAuth step,
  loaded via `--plugin-dir` from a directory that is not the plugin's
  own root (proving "available from any directory" actually holds).
- `/help` → Custom commands shows every skill namespaced as
  `/caddie:<name>`.
- `/context` shows both agents (`lead-analyst`, `data-analyst`) and
  both output styles available.
- Running the same walkthrough a second time after `/reload-plugins`
  (having edited one `SKILL.md` trigger string in between) picks up
  the edit without restarting the session.

**Commit:** "Verify packaged caddie plugin end-to-end via --plugin-dir"

