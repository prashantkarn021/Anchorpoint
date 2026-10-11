"""The one live bank connection. In memory only, because the Plaid connector keeps its token there.

A restart drops it; connecting again (or a demo reset) creates a fresh sandbox Item, whose
transactions are planted relative to today.
"""

import threading
from datetime import UTC, datetime

from backend.app.connectors.plaid import PlaidConnector

_lock = threading.Lock()
_connector: PlaidConnector | None = None
_connected_at: datetime | None = None


def current() -> PlaidConnector | None:
    return _connector if _connected_at else None


def connected_at() -> datetime | None:
    return _connected_at


def connect(transactions: list[dict]) -> PlaidConnector:
    """Create a sandbox Item planted with `transactions`. Any previous Item is removed by
    the connector once the new one exists. Raises if the Plaid keys are missing or wrong."""
    global _connector, _connected_at
    with _lock:
        connector = _connector or PlaidConnector(transactions)
        connector.transactions = transactions
        connector.finish_auth({"public_token": connector.start_auth()})
        _connector, _connected_at = connector, datetime.now(UTC)
        return connector


def disconnect() -> None:
    global _connected_at
    with _lock:
        if _connector is not None and _connected_at is not None:
            _connected_at = None
            _connector.revoke()
