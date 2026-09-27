---
name: export
description: Generate a standalone PDF snapshot of a Caddie analysis project's notebook (named `<year>-Q<quarter>-<project-slug>.pdf`, not `notebook.pdf`), inputs and outputs included, for handing off outside a browser. Trigger on /caddie:export followed by a project name, or when a user asks to export, download, or get a PDF of a notebook.
---

# /caddie:export <project>

A project's notebook already has two other views: the live `marimo
edit` session, and a static `notebook.html` that `/caddie:ask` renders
automatically once an episode has an answer. Neither is great for
handing an analysis to someone who just wants to read it, print it, or
attach it to an email/ticket - that's what this PDF is for: one file,
both the code and the rendered outputs, no browser or caddie install
needed to open it. It's named `<year>-Q<quarter>-<project-slug>.pdf`
(e.g. `2026-Q3-did-npls-drop.pdf`) rather than a generic `notebook.pdf`,
so it stays identifiable once it's out of its own project folder -
several exports all called `notebook.pdf` would collide the moment
they land in the same email thread or downloads folder.

`caddie notebook-export` does the actual rendering (via `marimo export
pdf ... --webpdf`); this skill's job is to invoke it and relay the
result. The PDF also refreshes itself automatically, best-effort, in
the background after each `/caddie:ask` episode or `/caddie:explore`
turn - this skill is for triggering that refresh manually, or getting
the very first PDF for a project.

## Invoking the CLI

The command below assumes `caddie` is already on `PATH` (installed
separately from this plugin, e.g. via `uv tool install caddie`). If it
fails with `command not found`, point the user at `/caddie:install`
rather than guessing at a workaround.

## Steps

1. Resolve the project slug — the argument given, or the active
   project from earlier in the conversation (`/caddie:ask` or
   `/caddie:load`) if none was given. If neither is available, ask the
   user which project, or point them at `/caddie:list`.

2. Run:

   ```
   caddie notebook-export --project <slug>
   ```

3. Relay the `pdf:` path to the user - it's a snapshot, not a live
   link, so if the notebook changes later it won't update until this
   command (or the automatic background refresh) runs again.

## If the command fails

- `No project '<slug>' under ...`: the project doesn't exist yet under
  that name — check `/caddie:list`.
- Any other failure is the underlying error from `marimo export pdf`
  (nbconvert/Chromium) — relay it verbatim. A missing-Chromium error
  means `/caddie:install` or `/caddie:update` hasn't been run on this
  machine yet; point the user there rather than guessing at a fix.
