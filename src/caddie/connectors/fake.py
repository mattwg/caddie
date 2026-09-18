"""In-memory connector used to validate Caddie's connector interface and
invocation path without needing a real backend."""

from typing import Any


class FakeConnector:
    def __init__(self) -> None:
        self._authenticated = False

    def authenticate(self) -> None:
        self._authenticated = True

    def get_session(self) -> "FakeConnector":
        return self

    def execute(self, query: str) -> list[dict[str, Any]]:
        if query.strip().rstrip(";").upper() == "SELECT 1":
            return [{"1": 1}]
        return []

    def describe(self) -> dict[str, Any]:
        return {
            "backend": "fake",
            "profile": None,
            "mode": "in-memory",
            "authenticated": self._authenticated,
        }
