import pytest

from backend.app.connectors import gmail


@pytest.fixture(autouse=True)
def no_rate_limit_waits(monkeypatch):
    """Connector tests never sleep; a test that wants the retries sets the waits itself."""
    monkeypatch.setattr(gmail, "RATE_LIMIT_WAITS", ())
