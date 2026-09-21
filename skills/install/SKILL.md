---
name: install
description: One-time laptop bootstrap for Caddie — installs required tooling, resolves the org config yaml (or individual skill_repo/skills/connector flags), runs connector auth, and resolves the notebooks root. Trigger on "/caddie:install".
---

# /caddie:install

This skill never runs shell or install commands itself — it only invokes
the `caddie install` CLI (implemented in Caddie core) and relays or
interprets its output. All actual tool bootstrap, repo cloning, config
writing, connector authentication, and verification happens inside
that script, not here.

`caddie install` never blocks on an interactive prompt — it needs
either a `--config` source or the individual `--skill-repo`/`--skills`/
`--connector` flags, and fails fast with a clear error if none are
given. Always call it with every value already known passed as a flag.

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
   connector auth and notebooks-root verification below.

2. Otherwise, ask the user in chat (if not already stated in the
   conversation) for a config source:
   - a local path or `http(s)://` URL to their org's config yaml
     (providing `skill_repo`/`skills`/`connector`/connector settings),
     or
   - the individual values directly: `skill_repo` (a git URL or local
     path), one or more `skills` from that repo, and `connector` (e.g.
     `databricks`) — plus optionally a custom notebooks root, if they
     don't want the default `~/caddie/notebooks`.

   If a config source is available, read it yourself (fetch the URL,
   or read the local file) and propose its values to the user for
   confirmation rather than asking blind.

3. Run:

   ```
   caddie install --config <path-or-url>
   ```

   or, with individual values:

   ```
   caddie install --skill-repo <skill_repo> --skills <comma,separated,skills> --connector <connector> [--notebooks-root <path>]
   ```

   (flags override anything from `--config`.) This single run covers
   `skill_repo`/`skills`/`connector`/connector-setting resolution,
   `~/.caddie/caddie.yaml` creation, connector authentication
   (including any browser OAuth step — let the user know to expect a
   browser window), and creating the notebooks folder. It ends with a
   pass/fail summary for each step.

4. Relay the script's summary output to the user verbatim — do not
   reformat, reinterpret, or silently swallow a failure. If it exits
   non-zero, tell the user which step failed and show the error it
   printed.
