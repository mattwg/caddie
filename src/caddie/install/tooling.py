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
