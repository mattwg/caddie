---
name: install
description: One-time laptop bootstrap for Caddie — installs required tooling, resolves the org config yaml (or individual skill_repo/skills/connector flags), runs connector auth, and resolves the notebooks root. Trigger on "/caddie:install".
---

# /caddie:install

This skill is the one place allowed to run install commands directly
(bootstrapping `uv` and `caddie` itself, below) — everything after
that is delegated to the `caddie install` CLI (implemented in Caddie
core), whose output this skill just relays or interprets. Repo
cloning, config writing, connector authentication, and verification
all happen inside that script, not here.

`caddie install` never blocks on an interactive prompt — it needs
either a `--config` source or the individual `--skill-repo`/`--skills`/
`--connector` flags, and fails fast with a clear error if none are
given. Always call it with every value already known passed as a flag.

## Output style default

Independent of `caddie install`/`caddie.yaml`, and not tied to
whatever project this happens to be run from — most users run
`/caddie:install` outside any project. Check `~/.claude/settings.json`
for an `outputStyle` field. If it's already set, skip this step.
Otherwise write `"outputStyle": "business-owner"` into
`~/.claude/settings.json` (create the file with `{}` first if it
doesn't exist yet, and merge into any existing content — never
overwrite other keys). This is the user's global Claude Code settings
file, so it applies to every session on this machine going forward. No
need to ask the user — `business-owner` is the default for everyone
who hasn't already chosen a style; they can switch with
`/output-style` at any time.

## Steps

1. Check `uv --version`. If that fails, install `uv` first:

   ```
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Check `caddie --version`. If `caddie` is missing, it can only be
   installed from a `caddie_source` — a git URL or local path — found
   under a `caddie_source:` key in the org config yaml (the same file
   used as `--config` in step 5 below). Get that config source now
   (from the conversation, or by asking the user — same as step 4
   below), read the file yourself directly (fetch the URL, or read the
   local file — not through `caddie`, since it doesn't exist yet), and
   pull out its `caddie_source` value. Then run:

   ```
   uv tool install <caddie_source>
   ```

   If the config has no `caddie_source` field, or no config source is
   available at all yet: tell the user `caddie` isn't installed and
   there's no source to install it from, and stop here — don't guess
   at a PyPI package name or any other source.

3. Check whether `~/.caddie/caddie.yaml` already exists. If so, just run:

   ```
   caddie install
   ```

   and relay its output — it will report the file already exists,
   leave `skill_repo`/`skills`/`connector` as-is, and go straight to
   connector auth and notebooks-root verification below.

4. Otherwise, ask the user in chat (if not already stated in the
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

5. Run:

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

6. Relay the script's summary output to the user verbatim — do not
   reformat, reinterpret, or silently swallow a failure. If it exits
   non-zero, tell the user which step failed and show the error it
   printed.
