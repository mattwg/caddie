"""`caddie install` — tool bootstrap, caddie.default.yaml-seeded
prompts, and caddie.yaml resolution (skill_repo, skills, connector,
connector settings).

Connector auth/setup, identity resolution, and the notebooks root are
a later stage of install, not this module's concern.
"""

import argparse
from pathlib import Path

from caddie.config.loader import DEFAULT_CONFIG_PATH, load_config, save_config
from caddie.config.model import CaddieConfig
from caddie.install.defaults import load_defaults
from caddie.install.prompts import prompt_list, prompt_value
from caddie.install.skill_repo import resolve_skill_repo
from caddie.install.tooling import ensure_uv_installed


def add_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "install", help="Bootstrap Caddie on this machine."
    )
    parser.add_argument("--skill-repo", help="Org skill repo: git URL or local path.")
    parser.add_argument("--skills", help="Comma-separated skill names.")
    parser.add_argument("--connector", help="Connector plugin name, e.g. databricks.")
    parser.add_argument(
        "--config-path",
        help="Override the caddie.yaml path (mainly for testing).",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path) if args.config_path else DEFAULT_CONFIG_PATH

    ensure_uv_installed()

    if config_path.is_file():
        return _run_existing(config_path)
    return _run_fresh(args, config_path)


def _run_existing(config_path: Path) -> int:
    config = load_config(config_path)
    print(f"{config_path} already exists; using it as-is.")

    if config.skill_repo_path and Path(config.skill_repo_path).is_dir():
        return 0

    clone_root = config_path.parent / "skill_repo"
    skill_repo_path = resolve_skill_repo(config.skill_repo, clone_root)
    config.skill_repo_path = str(skill_repo_path)
    save_config(config, config_path)
    return 0


def _run_fresh(args: argparse.Namespace, config_path: Path) -> int:
    skill_repo = args.skill_repo or prompt_value("Skill repo (git URL or local path)")
    clone_root = config_path.parent / "skill_repo"
    skill_repo_path = resolve_skill_repo(skill_repo, clone_root)

    defaults = load_defaults(skill_repo_path)

    skills = (
        [s.strip() for s in args.skills.split(",") if s.strip()]
        if args.skills
        else prompt_list("Skills", defaults.get("skills"))
    )
    connector = args.connector or prompt_value("Connector", defaults.get("connector"))

    connector_settings = {}
    for key, value in defaults.items():
        if key in ("skills", "connector"):
            continue
        connector_settings[key] = prompt_value(
            f"{connector} {key}", str(value) if value is not None else None
        )

    config = CaddieConfig(
        skills=skills,
        skill_repo=skill_repo,
        connector=connector,
        connector_settings=connector_settings,
        skill_repo_path=str(skill_repo_path),
    )
    save_config(config, config_path)
    print(f"Wrote {config_path}")
    return 0
