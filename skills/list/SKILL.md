---
name: list
description: Discover existing Caddie analysis projects — most recently modified first, optionally filtered by an ls-style wildcard pattern or limited to the N most recent. Read-only; never touches a notebook. Trigger on "/caddie:list [pattern]".
---

# /caddie:list [pattern]

This skill never walks the filesystem itself — it only invokes the
`caddie list` CLI (implemented in Caddie core) and relays its output.
All globbing and mtime sorting happens inside that script.

## Invoking the CLI

The command below assumes `caddie` is already on `PATH` (installed
separately from this plugin, e.g. via `uv tool install caddie`). If it
fails with `command not found`, point the user at `/caddie:install`
rather than guessing at a workaround.

## Steps

1. Run:

   ```
   caddie list [pattern] [--recent N]
   ```

   - With no arguments, lists the current user's projects, most
     recently modified first.
   - Pass through a pattern the user gave verbatim (e.g. `/caddie:list
     "revenue-*"`) as the positional argument — it matches `ls`-style
     wildcards against project slugs.
   - Pass `--recent N` if the user asked to limit how many recent
     projects to see; `--recent` with no number defaults to 10.

2. Relay the output as-is:
   - Each line is a project slug and its last-modified time — enough
     for the user to pick one and run `/caddie:load <project>` next.
   - "no projects found" means exactly that — report it plainly, not
     as an error.

3. Never create, modify, delete, or execute a notebook as part of this
   command — it is a lookup only.
