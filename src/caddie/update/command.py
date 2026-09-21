"""`caddie update` — idempotent environment refresh.

Connector-agnostic: re-checks tooling, re-reads caddie.yaml in case the
user edited it, re-points/pulls skill_repo, re-syncs Python
dependencies, and leaves existing auth and notebooks untouched unless
the connector's auth has actually gone stale.
"""

import argparse
from pathlib import Path

from caddie.checks import print_summary, run_checks
from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config, save_config
from caddie.connectors.loader import load_connector_from_config
from caddie.install.marimo_pair import upgrade_marimo_pair_skill
from caddie.install.skill_repo import pull_skill_repo, resolve_skill_repo
from caddie.install.tooling import upgrade_uv


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "update", help="Idempotently refresh the Caddie environment."
    )
    parser.add_argument(
        "--config-path",
        help="Override the caddie.yaml path (mainly for testing).",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path) if args.config_path else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

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
            ("skill repo up to date", _refresh_skill_repo),
            ("caddie itself up to date", _upgrade_caddie),
            ("connector auth valid", _verify_connector_auth),
        ]
    )

    save_config(config, config_path)
    ok = print_summary(results)
    return 0 if ok else 1
