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

The command below assumes `caddie` is already on `PATH` (installed
separately from this plugin, e.g. via `uv tool install caddie`). If it
fails with `command not found`, point the user at `/caddie:install`
rather than guessing at a workaround.

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

3. Relay the script's pass/fail summary to the user verbatim — do not
   paraphrase, embellish, or attach detail (e.g. a commit hash) that
   the script itself didn't print. Two distinct repos are in play here
   and must never be conflated: the org's `skill_repo` (the skills
   content, checked by the "skill repo up to date" step) and `caddie`
   core itself (the CLI, checked by the "caddie itself up to date"
   step via `uv tool upgrade caddie`). Attributing one repo's state or
   commit to the other's step is wrong even if both happen to pass.
   Existing notebooks are never touched by this command; if a step
   fails, tell the user which one and show the error it printed.
