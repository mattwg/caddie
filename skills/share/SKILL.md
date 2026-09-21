---
name: share
description: Generate a standalone copy of a Caddie analysis project's notebook (notebook.portable.py) with no dependency on the caddie package itself, for handing to someone who doesn't have caddie installed. Trigger on /caddie:share followed by a project name, or when a user asks to share, hand off, or send a notebook to a colleague/teammate who doesn't use Caddie.
---

# /caddie:share <project>

The working notebook (`notebook.py`) always depends on `caddie` itself
— its `setup` cell loads `~/.caddie/caddie.yaml` and resolves the
connector through caddie's plugin loader, which is the right default
while a project is actively worked on (it always gets the latest
connector/template code). But it means the notebook only runs on a
machine with caddie installed and resolvable.

This skill produces a second file, `notebook.portable.py`, alongside
the working notebook: same cells, but with the `setup` cell replaced
by the literal source of the connector actually used plus the shared
charting template, instantiated directly from the project's saved
connector settings — no `caddie` import anywhere. `caddie
notebook-share` does the actual rewrite; this skill's job is to invoke
it and relay the result.

## Invoking the CLI

The command below assumes `caddie` is already on `PATH` (installed
separately from this plugin, e.g. via `uv tool install caddie`). If it
fails with `command not found`, tell the user to install `caddie`
first rather than guessing at a workaround.

## Steps

1. Resolve the project slug — the argument given, or the active
   project from earlier in the conversation (`/caddie:ask` or
   `/caddie:load`) if none was given. If neither is available, ask the
   user which project, or point them at `/caddie:list`.

2. Run:

   ```
   caddie notebook-share --project <slug>
   ```

3. Relay the `portable notebook:` path to the user, and make clear
   what "portable" does and doesn't mean:
   - It removes the dependency on the `caddie` package — the file runs
     with just `marimo edit --sandbox` (or `uv run --script`) on any
     machine with `uv`, no caddie checkout needed.
   - It does **not** remove the dependency on the data backend. The
     person opening it still needs their own working access to the
     same source (e.g. their own Databricks CLI profile) — sharing the
     notebook doesn't share credentials or a connection.
   - It's a **snapshot**, not a live link to the working notebook. If
     the connector or shared charting template changes later, or the
     project's connector settings change, re-run `/caddie:share` to
     refresh it — it won't happen automatically.

## If the command fails

- `No project '<slug>' under ...`: the project doesn't exist yet under
  that name — check `/caddie:list`.
- `No project state at ...; run notebook-start before notebook-share.`:
  the project has no `notebook.py` yet, or its state file is missing —
  point the user at `/caddie:ask` to create it first.
- Any other failure is the underlying error from resolving the
  project's connector or reading its source — relay it verbatim rather
  than guessing at a fix.
