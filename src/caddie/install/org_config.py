"""Loads an org's caddie config yaml — the source of skill_repo/skills/
connector defaults for `caddie install`, now that there's no repo
checkout sitting next to it to discover a caddie.default.yaml from
(see requirements-plugin.md, "Config yaml source (first pass)").

Accepts either a local path (absolute or `~`-expanded, same existence
check as `resolve_skill_repo`'s local-candidate branch) or an
http(s):// URL, fetched via stdlib `urllib.request`. Nothing is
cached: re-running re-fetches.
"""

import urllib.request
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

_yaml = YAML(typ="safe")


class OrgConfigError(Exception):
    pass


def load_org_config(source: str) -> dict[str, Any]:
    if source.startswith("http://") or source.startswith("https://"):
        text = _fetch_url(source)
    else:
        text = _read_local(source)

    data = _yaml.load(text)
    return data or {}


def _read_local(source: str) -> str:
    path = Path(source).expanduser()
    if not path.is_file():
        raise OrgConfigError(f"Config yaml not found at {path}.")
    return path.read_text()


def _fetch_url(source: str) -> str:
    try:
        with urllib.request.urlopen(source, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except Exception as exc:
        raise OrgConfigError(f"Failed to fetch config yaml from {source}: {exc}") from exc
