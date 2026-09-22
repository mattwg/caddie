"""Databricks connector plugin.

Talks to Databricks over Spark Connect (`databricks-connect`), using an
OAuth-authenticated Databricks CLI profile — never a pasted personal
access token. `host` and `profile` come from the user's `caddie.yaml`
connector settings; this module has no knowledge of any specific
workspace or org.
"""

import configparser
import subprocess
from pathlib import Path
from typing import Any

DATABRICKS_CFG_PATH = Path.home() / ".databrickscfg"
DEFAULT_PROFILE = "caddie"


class DatabricksAuthError(Exception):
    """Raised when authenticate() can't proceed (e.g. no host for a new profile)."""


def _profile_exists(profile: str, cfg_path: Path = DATABRICKS_CFG_PATH) -> bool:
    if not cfg_path.is_file():
        return False
    parser = configparser.ConfigParser()
    parser.read(cfg_path)
    return profile in parser.sections()


class DatabricksConnector:
    def __init__(self, host: str | None = None, profile: str = DEFAULT_PROFILE) -> None:
        self.profile = profile
        self.host = host
        self._authenticated = False
        self._session: Any = None

    def check_config(self) -> None:
        """Raise early if the settings on hand can't authenticate.

        Called before any other install/update steps run, so a missing
        `host` is reported immediately rather than after other checks
        (uv, marimo-pair, notebooks root) have already run.
        """
        if not _profile_exists(self.profile) and not self.host:
            raise DatabricksAuthError(
                f"No Databricks CLI profile named '{self.profile}' exists yet, "
                "and no 'host' setting was provided to create one."
            )

    def authenticate(self) -> None:
        self.check_config()
        if _profile_exists(self.profile):
            cmd = ["databricks", "auth", "login", "--profile", self.profile]
        else:
            cmd = [
                "databricks",
                "auth",
                "login",
                "--host",
                self.host,
                "--profile",
                self.profile,
            ]
        subprocess.run(cmd, check=True)
        self._authenticated = True

    def get_session(self) -> Any:
        if self._session is None:
            from databricks.connect import DatabricksSession

            self._session = (
                DatabricksSession.builder.profile(self.profile)
                .serverless(True)
                .getOrCreate()
            )
        return self._session

    def execute(self, query: str) -> Any:
        return self.get_session().sql(query)

    def describe(self) -> dict[str, Any]:
        return {
            "backend": "databricks",
            "profile": self.profile,
            "host": self.host,
            "mode": "serverless",
            "authenticated": self._authenticated,
        }
