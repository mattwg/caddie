---
name: caddie-install
description: One-time laptop bootstrap for Caddie — installs required tooling, resolves the org skill repo and its skills/connector, runs connector auth, resolves identity and the notebooks root, and writes ~/.caddie/caddie.yaml. Trigger on "/caddie-install".
---

# /caddie-install

This skill never runs shell or install commands itself — it only invokes
the `caddie install` CLI (implemented in Caddie core) and relays or
interprets its output. All actual tool bootstrap, repo cloning, config
writing, connector authentication, and verification happens inside
that script, not here.

`caddie install` can prompt interactively on a real terminal, but this
skill can't answer an interactive stdin prompt on the user's behalf, so
always call it with every value already known passed as a flag.

## Invoking the CLI

Every `caddie ...` command below assumes `caddie` is on `PATH`. If the
working directory is a checkout of the Caddie project itself (look for
a `pyproject.toml` with `name = "caddie"` at or above the working
directory), the `caddie` entry point only exists inside that project's
own virtualenv — running it bare will fail with `command not found`.
In that case, prefix every `caddie` command below with `uv run`, e.g.
`uv run caddie install` (`uv run` also handles syncing dependencies
the first time, so no separate sync step is needed). Check for this
once at the start rather than discovering it after a failed call.

`uv run` itself needs `uv` installed. Check with `uv --version`; if
that fails, install it with:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

before running any `caddie` command. This is the one piece of setup
Caddie can't bootstrap through its own CLI, since the CLI can't run at
all without `uv` already present — everything after that (the pinned
Python version, dependencies, other tooling) is handled by `caddie
install` itself.

## Steps

1. Check whether `~/.caddie/caddie.yaml` already exists. If so, just run:

   ```
   caddie install
   ```

   and relay its output — it will report the file already exists,
   leave `skill_repo`/`skills`/`connector` as-is, and go straight to
   connector auth, identity, and notebooks-root verification below.

2. Otherwise, ask the user in chat (if not already stated in the
   conversation) for:
   - `skill_repo` — their org's skill repo, a git URL or local path.
   - `skills` — one or more skill names from that repo to enable.
   - `connector` — the data connector to use (e.g. `databricks`).
   - optionally, a custom notebooks root, if they don't want the
     default `~/caddie/notebooks`.

   If the repo has a `caddie.default.yaml`, its `skills`/`connector`
   values (and any connector settings, e.g. a Databricks `host`) are
   good defaults to offer the user instead of asking blind — you can
   discover this by reading `caddie.default.yaml` at the root of the
   skill repo yourself before asking (clone/checkout first if it's a
   remote URL you don't have locally), and proposing its values.

3. Run:

   ```
   caddie install --skill-repo <skill_repo> --skills <comma,separated,skills> --connector <connector> [--notebooks-root <path>]
   ```

   This single run covers `skill_repo`/`skills`/`connector`/connector-
   setting resolution, `~/.caddie/caddie.yaml` creation, connector
   authentication (including any browser OAuth step — let the user
   know to expect a browser window), identity resolution, and creating
   the notebooks folder. It ends with a pass/fail summary for each
   step.

4. Relay the script's summary output to the user verbatim — do not
   reformat, reinterpret, or silently swallow a failure. If it exits
   non-zero, tell the user which step failed and show the error it
   printed.
