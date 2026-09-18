"""Backend-agnostic data connector interface.

Every connector plugin, regardless of backend, implements this shape.
Caddie core calls these four methods directly; it never knows anything
about a specific backend.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Connector(Protocol):
    def authenticate(self) -> None:
        """Perform whatever one-time or per-session auth the backend needs."""
        ...

    def get_session(self) -> Any:
        """Return a live session/handle a notebook cell can query against."""
        ...

    def execute(self, query: str) -> Any:
        """Run a query and return a DataFrame-like result."""
        ...

    def describe(self) -> dict[str, Any]:
        """Return metadata (backend name, profile/account, connection mode)."""
        ...
