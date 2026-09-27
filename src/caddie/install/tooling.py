"""Bootstraps the tools `caddie install` needs on a fresh machine."""

import shutil
import subprocess
import sys


def ensure_uv_installed() -> None:
    if shutil.which("uv") is not None:
        return
    subprocess.run(
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        shell=True,
        check=True,
    )


def ensure_chromium_installed() -> None:
    """PDF export (`caddie notebook-export`, `notebook/export.py`)
    renders via nbconvert's `--webpdf` exporter, which needs a
    Playwright-managed Chromium - not a pip dependency, so it isn't
    pulled in by `nbconvert[webpdf]` itself. `playwright install
    chromium` is idempotent (a no-op if already cached), so this is
    safe to run on every `install`/`update`."""
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
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
