"""Resolves the current user's identity for notebook storage paths.

Per requirements.md: identity comes from `git config user.email`,
falling back to the OS user when git has no email configured (or isn't
installed) — never prompted for, since it's always derivable.
"""

import getpass
import subprocess


def resolve_username() -> str:
    email = _git_user_email()
    if email:
        local_part = email.split("@", 1)[0]
        if local_part:
            return local_part
    return getpass.getuser()


def _git_user_email() -> str | None:
    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout.strip() or None
