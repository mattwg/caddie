# Caddie — Claude Code Plugin Packaging

## Purpose

Today, using Caddie means cloning its repo (or an org's fork of it) and
opening that folder in Claude Code, because Claude Code only reads
`.claude/skills`, `.claude/agents`, and `.claude/output-styles` from the
current working directory. Every command (`/caddie-ask`, `/caddie-install`,
etc.) only works from inside that folder.

This document specifies packaging Caddie as a [Claude Code
plugin](https://code.claude.com/docs/en/plugins) named `caddie`, so its
skills and agents are available from any directory once installed, with
no clone and no `cd` required. It also specifies the one behavior change
that packaging forces: how `/caddie:install` gets its configuration, now
that there's no repo checkout to hold a `caddie.default.yaml` next to.

## Non-goals for this pass

- **Auto-triggering install on first use.** A skill-frontmatter hook with
  `once: true` could fire setup automatically the first time any
  `/caddie:*` skill runs. Considered and set aside in favor of a plain,
  explicit `/caddie:install` skill the user runs themselves — see Open
  questions for revisiting this later.
- **Publishing to a marketplace**, community or private. This spec covers
  the plugin's own structure and its config-loading behavior, not how an
  org distributes or updates it. `/caddie-update`'s tooling/dependency/
  connector-auth refresh role is unaffected either way.
- **Removing the org skill-repo concept.** An org's actual analytics
  skill content (table names, metric definitions, connector settings)
  still has to come from somewhere — a git URL or local path, resolved
  the same way `src/caddie/install/skill_repo.py` does today. This pass
  only changes *how `/caddie:install` learns that skill_repo value*, not
  what happens once it has it.
- **Authentication for a URL-hosted config file.** First pass assumes the
  hosted YAML is reachable without credentials (e.g. on an internal
  network). See Open questions.
- **Windows support** — already out of scope elsewhere; unchanged here.

## Naming

The plugin is named `caddie`. Skill folders are renamed so their
namespaced command is short, rather than doubling the plugin name:

| Today                                | Plugin skill folder | Resulting command       |
| ------------------------------------- | -------------------- | ------------------------ |
| `.claude/skills/caddie-install`       | `skills/install`     | `/caddie:install`        |
| `.claude/skills/caddie-ask`           | `skills/ask`         | `/caddie:ask`             |
| `.claude/skills/caddie-list`          | `skills/list`        | `/caddie:list`            |
| `.claude/skills/caddie-load`          | `skills/load`        | `/caddie:load`            |
| `.claude/skills/caddie-edit`          | `skills/edit`        | `/caddie:edit`            |
| `.claude/skills/caddie-share`         | `skills/share`       | `/caddie:share`           |
| `.claude/skills/caddie-update`        | `skills/update`      | `/caddie:update`          |
| `.claude/skills/caddie-add-dependency`| `skills/add-dependency` | `/caddie:add-dependency` |

Every `SKILL.md`'s own trigger text (e.g. `Trigger on "/caddie-install"`)
and every cross-reference to the old command form (README, other
`SKILL.md` files) needs updating to the `/caddie:<name>` form as part of
this change — a stale trigger string is a silent miss, not an error.

## Plugin structure

Per the [plugin directory
layout](https://code.claude.com/docs/en/plugins#plugin-structure-overview):

- `.claude-plugin/plugin.json` — `name: "caddie"`, `description`,
  `version`.
- `skills/` — the renamed skill folders above, moved from
  `.claude/skills/*`.
- `agents/` — `lead-analyst.md`, `data-analyst.md`, moved from
  `.claude/agents/*`.
- `bin/` — not used; the plugin still shells out to the `caddie` CLI,
  which is installed separately (via `uv tool install` or equivalent),
  not bundled as a plugin executable.
- `output-styles/` — `business-owner.md`, `data-analyst.md`, moved from
  `.claude/output-styles/*`.

Verified against the [plugins reference](https://code.claude.com/docs/en/plugins-reference):
`output-styles/` is a standard plugin directory (default location for
output style definitions), with an optional `outputStyles` field in
`plugin.json` to point at a different path. The shorter directory list
in the main [plugins guide](https://code.claude.com/docs/en/plugins#plugin-structure-overview)
just omits it; the reference page is authoritative. Plugins ship
output styles as a first-class component — no workaround needed. The
existing `caddie-install/SKILL.md` workaround (asking the user in chat
and writing `outputStyle` into `.claude/settings.local.json` directly)
can be dropped as part of this migration.

## `/caddie:install` requirements

**What changes from today's `/caddie-install`:** the skill no longer has
a repo checkout sitting next to it to discover a `caddie.default.yaml`
from. It needs a **caddie config yaml** to be told where to look instead.

**What doesn't change:** everything downstream of learning
`skill_repo`/`skills`/`connector` — resolving the skill repo, connector
auth, notebooks-root setup, and writing `~/.caddie/caddie.yaml` — is
exactly the existing `caddie install` CLI flow (`src/caddie/install/*`).
This spec only changes where the initial values come from. The one
exception is identity/username resolution, which this pass removes
outright — see Dropping identity resolution below.

### Config yaml source (first pass)

`/caddie:install` accepts the config yaml from either:

- **A local path** — an absolute or `~`-expanded path on the user's own
  machine, read as-is (same existence check as
  `resolve_skill_repo`'s local-candidate branch today).
- **A URL** — fetched over HTTP(S) at install time. No caching of the
  fetched file is specified for this pass; re-running `/caddie:install`
  re-fetches.

If neither is already known (stated in chat, or passed as an argument to
the skill), the skill asks the user for one before doing anything else.

**Decision: drop the blind, field-by-field interactive prompting in
`src/caddie/install/prompts.py` (`prompt_value`/`prompt_list`,
blocking on `input()`).** It only ever served one caller: a human typing
answers directly into a bare terminal running `caddie install` with no
flags at all. Every Claude Code-driven path already avoids it —
`caddie-install/SKILL.md` states it can't answer a stdin prompt on the
user's behalf, so it always resolves values itself (via chat, or a
discovered `caddie.default.yaml`) and passes them as flags. So in the
one usage pattern that matters, that code already never runs. Once a
config yaml (local or URL) is the primary source, it's a second,
redundant "fill in what's missing" mechanism alongside the yaml, with no
remaining caller that needs it.

**What stays:** the CLI flags themselves (`--skill-repo`, `--skills`,
`--connector`) — they're what the skill relies on to pass resolved
values non-interactively, what tests/scripts use, and they let a value
from the yaml be overridden without editing it.

**New failure mode:** if `caddie install` is given neither a config
yaml (local/URL) nor the individual flags, it fails fast with a clear
error telling the user to supply one, instead of falling into
`input()`.

### Config yaml content

Same shape as today's `caddie.default.yaml`: `skill_repo`, `skills`,
`connector` (plus connector settings, e.g. a Databricks `host`), and
optionally a custom notebooks root. Once loaded, `/caddie:install`
proposes these values to the user exactly as `caddie-install/SKILL.md`
does today when it finds a `caddie.default.yaml` — confirm rather than
blind-ask.

**Decision: the config yaml (local/URL) is the only source.** Today,
`caddie install` also reads a `caddie.default.yaml` from inside the
resolved `skill_repo` itself (`_resolve_fresh` in
`src/caddie/install/command.py` calls `load_defaults(skill_repo_path)`,
which reads `skill_repo_path / "caddie.default.yaml"` —
`src/caddie/install/defaults.py`). That lookup is dropped as part of
this pass: nothing is read from inside `skill_repo` anymore, so there
is no second source and no precedence question. `load_defaults` and
its call site are removed; `skill_repo` is resolved and used only for
loading skills, never scanned for its own config file.

### `/caddie:update` and the config yaml

**Decision: `/caddie:update` re-fetches the config yaml.** If the
source is a URL, it re-fetches and re-reads it; if it's a local path,
it re-reads it. This lets an org roll out a changed `skill_repo` or
connector setting to existing installs via `/caddie:update`, not only
via a fresh `/caddie:install`. Resolved values are re-proposed for
confirmation the same way a fresh install does, alongside `/caddie:update`'s
existing tooling/dependency/connector-auth refresh role.

## Dropping identity resolution

**Requirement for this pass: remove username/identity resolution from
Caddie entirely.** It is not optional or deferred — the plugin's
`/caddie:install` and every notebook-path-resolving command listed below
must stop resolving or storing a username as part of this work.

`resolve_username` (`src/caddie/install/identity.py`) exists solely to
build a per-user path segment: `~/caddie/notebooks/<username>/<project-
slug>/notebook.py` (`.specs/requirements.md`, Storage). That's
unnecessary overhead once notebooks are purely local to one laptop —
`~/caddie/notebooks` is already scoped to the single OS user who owns
`~`, so a `<username>` subfolder under it never disambiguates anything
in practice. Resolving it via `git config user.email` (with an OS-user
fallback) is real complexity — a subprocess call, a fallback path, a
config field (`config.username`) — for a path segment that isn't doing
real work.

**Requirement:** drop `identity.py` and the `<username>` path segment
entirely. Notebook paths become `~/caddie/notebooks/<year>/Q<quarter>/
<month>/<date>/<project-slug>/notebook.py` — the year/quarter/month/date
partition folded in the pre-existing todo item on year/month/day
organization (`.specs/todo.md`) alongside dropping `<username>`, since
both touch the same path segment. `find_project_dir`
(`install/notebooks.py`) resolves a bare `--project <slug>` to wherever
its date partition put it, so the seven call sites
(`caddie.notebook.start`, `.edit`, `.share`, `.add_dependency`,
`.render`, `caddie.list.command`, and `caddie.install.command` itself)
never need to know or reconstruct a project's partition — same as they
never resolved `<username>` themselves before. The `username` field on
`config/model.py`'s config object is gone along with
`config.username or resolve_username()`.

Not itself caused by the plugin move — a local laptop tool never needed
multi-user disambiguation — but the plugin work is what surfaces it,
since `/caddie:install`'s new config-yaml-driven flow (above) is already
touching the same install path this would change.

## Relationship to existing interfaces

- `/caddie:install` still only calls `caddie install` (with resolved
  flags), same as `caddie-install/SKILL.md` does today per its "never
  runs shell or install commands itself" rule. See "Caddie's own root
  is no longer knowable" below for the parts of the CLI itself that do
  change.
- `~/.caddie/caddie.yaml`'s format and role are unchanged. The config
  yaml (local/URL) is a new **input** to producing it, not a
  replacement for it.
- `.specs/requirements.md`'s analytics-skill and connector-plugin
  interfaces are unaffected — this pass only changes how
  `/caddie:install` learns which skill repo and connector to resolve,
  not what happens once it has resolved them.

## Caddie's own root is no longer knowable

**Problem:** several places in the CLI locate "the caddie project" by
walking up from the installed package's own file path —
`CADDIE_CORE_ROOT = Path(__file__).resolve().parents[3]`
(`install/command.py`, `update/command.py`) and `caddie_root()` in
`notebook/dependencies.py`. That only resolves to something real when
`caddie` runs from an editable git checkout. Once the CLI is installed
separately (via `uv tool install` or equivalent, per Plugin structure
above), there is no `.claude/skills/` or `pyproject.toml` sitting above
the installed package anymore, so all three break silently or fail.

**Decision — three fixes, none of which require bundling the CLI's
own dependencies inside the plugin:**

1. **marimo-pair skill install target.** `install_marimo_pair_skill`/
   `upgrade_marimo_pair_skill` (`install/marimo_pair.py`) keep doing
   exactly what they do today — shelling out to
   `skills add marimo-team/marimo-pair` — but install into
   `~/.claude/skills/marimo-pair` instead of
   `CADDIE_CORE_ROOT/.claude/skills/marimo-pair`. `~/.claude/skills` is
   a fixed, well-known user-scope location Claude Code always reads
   from, independent of where caddie's own code is installed or which
   directory a command is run from. One-line change: swap
   `CADDIE_CORE_ROOT` for `Path.home()` at the two call sites.
2. **`/caddie:update`'s `uv sync` step.** That step re-syncs a dev
   checkout's dependencies from its `pyproject.toml` — meaningless
   once the CLI is an installed tool rather than a checkout. Replace
   the `pyproject.toml`-exists check and `uv sync` call
   (`update/command.py`) with `uv tool upgrade caddie`, run
   unconditionally, to keep the installed CLI itself current.
3. **Notebook dependency-version pinning.** `caddie_root()` and
   `_caddie_project_metadata()` (`notebook/dependencies.py`) parse
   caddie's own `pyproject.toml` off disk to pin dependency versions
   into each generated notebook's PEP 723 header. Replace this with
   `importlib.metadata` (`importlib.metadata.version("caddie")`,
   `importlib.metadata.requires("caddie")`) — the standard,
   distribution-agnostic way to read a package's own declared
   dependencies, which works identically whether caddie is an editable
   checkout or an installed wheel.

