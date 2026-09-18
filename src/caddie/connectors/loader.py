"""Resolves a connector plugin by name.

Connectors register themselves as entry points in the
"caddie.connectors" group (see pyproject.toml for the built-in "fake"
connector). A real org connector (e.g. Databricks) is just another
installed package registering the same entry point group — this
loader has no knowledge of any specific backend.
"""

from importlib.metadata import EntryPoint, entry_points

from caddie.connectors.base import Connector

_ENTRY_POINT_GROUP = "caddie.connectors"


class ConnectorNotFoundError(Exception):
    def __init__(self, name: str, available: list[str]) -> None:
        available_str = ", ".join(sorted(available)) if available else "none"
        super().__init__(
            f"No connector plugin named '{name}' is installed. "
            f"Available: {available_str}."
        )
        self.name = name
        self.available = available


def _available_entry_points() -> dict[str, EntryPoint]:
    return {ep.name: ep for ep in entry_points(group=_ENTRY_POINT_GROUP)}


def load_connector(name: str, **kwargs: object) -> Connector:
    """Instantiate the named connector plugin.

    Raises ConnectorNotFoundError if no connector is registered under
    that name, rather than letting a raw ImportError/KeyError surface.
    """
    available = _available_entry_points()
    if name not in available:
        raise ConnectorNotFoundError(name, list(available.keys()))

    connector_cls = available[name].load()
    return connector_cls(**kwargs)
