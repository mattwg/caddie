"""Bootstraps the tools `caddie install` needs on a fresh machine."""

import shutil
import subprocess


def ensure_uv_installed() -> None:
    if shutil.which("uv") is not None:
        return
    subprocess.run(
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        shell=True,
        check=True,
    )


def upgrade_uv() -> None:
    """Best-effort re-check of the `uv` version; a no-op when already current.

    Some installs of `uv` (e.g. via a system package manager) don't
    support `uv self update`; that's not a caddie-update failure, so
    it's swallowed rather than propagated.
    """
    ensure_uv_installed()
    subprocess.run(
        ["uv", "self", "update"],
        check=False,
        capture_output=True,
    )
