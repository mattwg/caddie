---
name: update
description: Idempotent refresh of an existing Caddie setup — re-checks tooling, re-reads caddie.yaml for edits (skill/connector/skill_repo changes), pulls the skill repo, re-syncs Python dependencies, and re-authenticates the connector only if its auth has gone stale. Trigger on "/caddie:update".
---

# /caddie:update

This skill never runs shell or install commands itself — it only
invokes the `caddie update` CLI (implemented in Caddie core) and
relays or interprets its output. All actual tool/version checks, repo
pulling, dependency syncing, and connector re-auth happen inside that
script, not here.

## Invoking the CLI

The command below assumes `caddie` is on `PATH`. If the working
directory is a checkout of the Caddie project itself (look for a
`pyproject.toml` with `name = "caddie"` at or above the working
directory), the `caddie` entry point only exists inside that project's
own virtualenv — running it bare will fail with `command not found`.
In that case, prefix it with `uv run`, e.g. `uv run caddie update`.
Check for this once at the start rather than discovering it after a
failed call.

## Steps

1. Run:

   ```
   caddie update
   ```

   with no arguments — `caddie update` reads `~/.caddie/caddie.yaml`
   itself and needs nothing else from the user, including after they
   hand-edited it (e.g. switched `connector` or `skill_repo`).

2. If the connector's auth has expired or was removed, `caddie update`
   re-runs authentication itself (which may involve a browser OAuth
   step) — let the user know to expect that rather than treating it as
   an unexpected prompt.

3. Relay the script's pass/fail summary to the user verbatim. Existing
   notebooks are never touched by this command; if a step fails, tell
   the user which one and show the error it printed.
