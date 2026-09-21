---
name: add-dependency
description: Add a Python package to one Caddie analysis project's notebook, isolated to that notebook's own sandboxed environment rather than caddie's own shared venv. Trigger on /caddie:add-dependency followed by a project name and package, or when a user's analysis code (in /caddie:ask or /caddie:edit) needs a package that isn't already available and they ask how to install it.
---

# /caddie:add-dependency <project> <package>

Every generated notebook carries its own PEP 723 `# /// script`
dependency header (written by `caddie.notebook.dependencies`, read by
`marimo edit --sandbox` — see `/caddie:edit`). This skill adds a
package to that header for one project's notebook, without touching
caddie's own `pyproject.toml` or shared `.venv` — so a heavy or
conflicting package one notebook needs (e.g. `scikit-learn`,
`statsmodels`) never has to be reconciled against caddie's own
dependencies or any other notebook's.

## Invoking the CLI

The command below assumes `caddie` is on `PATH`. If the working
directory is a checkout of the Caddie project itself (look for a
`pyproject.toml` with `name = "caddie"` at or above the working
directory), the `caddie` entry point only exists inside that project's
own virtualenv — prefix with `uv run`, e.g. `uv run caddie
notebook-add-dependency ...`. Check for this once rather than
discovering it after a failed call.

## Steps

1. Resolve the project slug — the argument given, or the active
   project from earlier in the conversation (`/caddie:ask` or
   `/caddie:load`) if none was given. If neither is available, ask the
   user which project, or point them at `/caddie:list`.

2. Run:

   ```
   caddie notebook-add-dependency --project <slug> <package>
   ```

   `<package>` is any requirement `uv add` accepts — a bare name
   (`scikit-learn`), a version constraint (`"pandas>=2"`), or an extra
   (`"boto3[s3]"`). Quote it if it contains characters the shell would
   otherwise interpret.

3. Relay the `added:` / `notebook:` lines to the user, and tell them
   the package takes effect the next time that notebook's live editor
   is (re)opened with `/caddie:edit` — not retroactively in an editor
   session already running, and not in `/caddie:ask`'s own guided
   execution (that runs in-process against caddie's shared venv, since
   it has to share a live connector session; it's limited to whatever
   caddie itself already has installed).

## If the command fails

- `No project '<slug>' under ...`: the project doesn't exist yet under
  that name — check `/caddie:list`, or confirm the notebook has been
  started with `/caddie:ask` at least once.
- `uv is required ...`: `uv` isn't on `PATH` in this environment; point
  the user at `/caddie:install` or `/caddie:update`.
- Any other failure is `uv add`'s own stderr (e.g. the package name
  doesn't resolve on the configured index) — relay it verbatim rather
  than guessing at a fix.
