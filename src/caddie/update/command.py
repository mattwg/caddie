"""`caddie update` — idempotent environment refresh.

Connector-agnostic: re-checks tooling, re-reads caddie.yaml in case the
user edited it, re-fetches the org config yaml (local path or URL) and
re-proposes any changed skill_repo/skills/connector values the same
way a fresh install does, re-points/pulls skill_repo, keeps the
installed `caddie` tool itself current, and leaves existing auth and
notebooks untouched unless the connector's auth has actually gone
stale.
"""

import argparse
from pathlib import Path

from caddie.checks import print_summary, run_checks
from caddie.config.loader import (
    DEFAULT_CONFIG_PATH,
    NON_CONNECTOR_KEYS,
    load_config,
    save_config,
)
from caddie.connectors.loader import load_connector_from_config
from caddie.install.marimo_pair import upgrade_marimo_pair_skill
from caddie.install.org_config import OrgConfigError, load_org_config
from caddie.install.skill_repo import pull_skill_repo, resolve_skill_repo
from caddie.install.tooling import upgrade_uv


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "update", help="Idempotently refresh the Caddie environment."
    )
    parser.add_argument(
        "--config",
        help="Org config yaml source (local path or http(s):// URL) to "
        "re-fetch from; defaults to the source recorded at install time.",
    )
    parser.add_argument(
        "--config-path",
        help="Override the caddie.yaml path (mainly for testing).",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path) if args.config_path else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    config_source = args.config or config.config_source
    if config_source:
        config.config_source = config_source

    def _refresh_org_config() -> None:
        if not config_source:
            return
        try:
            org_config = load_org_config(config_source)
        except OrgConfigError as exc:
            raise RuntimeError(str(exc))

        for key in ("skill_repo", "skills", "connector"):
            if key not in org_config:
                continue
            new_value = org_config[key]
            old_value = getattr(config, key)
            if new_value != old_value:
                print(f"{key}: {old_value!r} -> {new_value!r}")
                setattr(config, key, new_value)

        connector_settings = {
            key: value
            for key, value in org_config.items()
            if key not in NON_CONNECTOR_KEYS
        }
        for key, value in connector_settings.items():
            old_value = config.connector_settings.get(key)
            if value != old_value:
                print(f"{key}: {old_value!r} -> {value!r}")
        config.connector_settings.update(connector_settings)

    def _refresh_skill_repo() -> None:
        clone_root = config_path.parent / "skill_repo"
        skill_repo_path = resolve_skill_repo(config.skill_repo, clone_root)
        config.skill_repo_path = str(skill_repo_path)
        pull_skill_repo(skill_repo_path)

    def _upgrade_caddie() -> None:
        import subprocess

        subprocess.run(["uv", "tool", "upgrade", "caddie"], check=True)

    def _verify_connector_auth() -> None:
        connector = load_connector_from_config(config)
        try:
            connector.execute("SELECT 1")
        except Exception:
            connector.authenticate()
            connector.execute("SELECT 1")

    results = run_checks(
        [
            ("uv up to date", upgrade_uv),
            ("marimo-pair skill up to date", upgrade_marimo_pair_skill),
            ("org config up to date", _refresh_org_config),
            ("skill repo up to date", _refresh_skill_repo),
            ("caddie itself up to date", _upgrade_caddie),
            ("connector auth valid", _verify_connector_auth),
        ]
    )

    save_config(config, config_path)
    ok = print_summary(results)
    return 0 if ok else 1
