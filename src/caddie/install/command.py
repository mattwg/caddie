"""`caddie install` — tool bootstrap, config-yaml/flag-driven resolution
of skill_repo/skills/connector, caddie.yaml resolution, connector
setup, identity, and notebooks root.

The org skill repo itself is never scanned for its own defaults file
(dropped per requirements-plugin.md's "Config yaml content" decision)
— skill_repo is resolved and used only for loading skills.

Whether or not `~/.caddie/caddie.yaml` already existed, install always
finishes by running the connector's auth, resolving identity/notebooks
root, and verifying the setup end to end — only the skill_repo/skills/
connector prompting step is skipped once the file exists.
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
from caddie.config.model import CaddieConfig
from caddie.connectors.loader import load_connector_from_config
from caddie.install.marimo_pair import install_marimo_pair_skill
from caddie.install.notebooks import ensure_notebooks_dir, resolve_notebooks_root
from caddie.install.org_config import OrgConfigError, load_org_config
from caddie.install.skill_repo import resolve_skill_repo
from caddie.install.tooling import ensure_uv_installed


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "install", help="Bootstrap Caddie on this machine."
    )
    parser.add_argument(
        "--config",
        help="Org config yaml: a local path or http(s):// URL, providing "
        "skill_repo/skills/connector defaults.",
    )
    parser.add_argument("--skill-repo", help="Org skill repo: git URL or local path.")
    parser.add_argument("--skills", help="Comma-separated skill names.")
    parser.add_argument("--connector", help="Connector plugin name, e.g. databricks.")
    parser.add_argument(
        "--notebooks-root",
        help="Override the default ~/caddie/notebooks root for generated notebooks.",
    )
    parser.add_argument(
        "--config-path",
        help="Override the caddie.yaml path (mainly for testing).",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path) if args.config_path else DEFAULT_CONFIG_PATH

    if not config_path.is_file() and not (args.config or args.skill_repo or args.skills or args.connector):
        raise SystemExit(
            "caddie install needs a config source: pass --config <path-or-url>, "
            "or --skill-repo/--skills/--connector directly."
        )

    if config_path.is_file():
        config = _resolve_existing(config_path)
    else:
        try:
            config = _resolve_fresh(args, config_path)
        except OrgConfigError as exc:
            raise SystemExit(str(exc))

    ok = _finish_install(config, config_path, args)
    return 0 if ok else 1


def _resolve_existing(config_path: Path) -> CaddieConfig:
    config = load_config(config_path)
    print(f"{config_path} already exists; using it as-is.")

    if not config.skill_repo_path or not Path(config.skill_repo_path).is_dir():
        clone_root = config_path.parent / "skill_repo"
        config.skill_repo_path = str(resolve_skill_repo(config.skill_repo, clone_root))

    return config


def _resolve_fresh(args: argparse.Namespace, config_path: Path) -> CaddieConfig:
    defaults = load_org_config(args.config) if args.config else {}

    skill_repo = args.skill_repo or defaults.get("skill_repo")
    if not skill_repo:
        raise SystemExit(
            "No skill_repo given: pass --skill-repo, or a --config yaml that "
            "defines one."
        )

    skills = (
        [s.strip() for s in args.skills.split(",") if s.strip()]
        if args.skills
        else list(defaults.get("skills") or [])
    )
    if not skills:
        raise SystemExit(
            "No skills given: pass --skills, or a --config yaml that defines "
            "some."
        )

    connector = args.connector or defaults.get("connector")
    if not connector:
        raise SystemExit(
            "No connector given: pass --connector, or a --config yaml that "
            "defines one."
        )

    clone_root = config_path.parent / "skill_repo"
    skill_repo_path = resolve_skill_repo(skill_repo, clone_root)

    connector_settings = {
        key: value for key, value in defaults.items() if key not in NON_CONNECTOR_KEYS
    }

    print(f"skill_repo: {skill_repo}")
    print(f"skills: {', '.join(skills)}")
    print(f"connector: {connector}")
    for key, value in connector_settings.items():
        print(f"{key}: {value}")

    return CaddieConfig(
        skills=skills,
        skill_repo=skill_repo,
        connector=connector,
        connector_settings=connector_settings,
        skill_repo_path=str(skill_repo_path),
        config_source=args.config,
    )


def _finish_install(
    config: CaddieConfig, config_path: Path, args: argparse.Namespace
) -> bool:
    """Connector setup, identity, notebooks root, and verification.

    Runs regardless of whether the config was just created or already
    existed, since these steps are what a plain re-run of `caddie
    install` is expected to (re)verify.
    """
    notebooks_root = Path(args.notebooks_root).expanduser() if args.notebooks_root else (
        Path(config.notebooks_root).expanduser()
        if config.notebooks_root
        else resolve_notebooks_root(None)
    )

    config.notebooks_root = str(notebooks_root)

    connector_holder: dict[str, object] = {}

    def _authenticate() -> None:
        connector = load_connector_from_config(config)
        connector_holder["connector"] = connector
        connector.authenticate()

    def _live_query() -> None:
        connector = connector_holder.get("connector")
        if connector is None:
            raise RuntimeError("skipped: connector authentication did not succeed")
        connector.execute("SELECT 1")

    results = run_checks(
        [
            ("uv installed", ensure_uv_installed),
            ("marimo-pair skill installed", install_marimo_pair_skill),
            ("notebooks root ready", lambda: ensure_notebooks_dir(notebooks_root)),
            ("connector authenticated", _authenticate),
            ("connector live query", _live_query),
        ]
    )

    save_config(config, config_path)
    return print_summary(results)
