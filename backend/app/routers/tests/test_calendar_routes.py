"""Calendar OAuth start and callback dispatch (Gmail's own route tests stay in test_oauth.py)."""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.routers.oauth import (
    calendar_connector,
    calendar_factory,
    gmail_connector,
)


class Fake:
    def __init__(self):
        self.finished_with = None

    def start_auth(self):
        return "https://accounts.google.com/o/oauth2/v2/auth?state=calendar.abc"

    def finish_auth(self, params):
        self.finished_with = params


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    gmail, calendar = Fake(), Fake()
    app.dependency_overrides[gmail_connector] = lambda: gmail
    app.dependency_overrides[calendar_connector] = lambda: calendar
    app.dependency_overrides[calendar_factory] = lambda: (lambda: calendar)
    try:
        c = TestClient(app, follow_redirects=False)
        c.gmail, c.calendar = gmail, calendar
        yield c
    finally:
        app.dependency_overrides.clear()


def test_calendar_start_returns_the_google_url(client):
    r = client.post("/api/connections/calendar/start")
    assert r.status_code == 200 and "state=calendar." in r.json()["redirect_url"]


def test_callback_sends_calendar_state_to_the_calendar_connector(client):
    r = client.get("/api/oauth/callback?code=abc&state=calendar.xyz")
    assert r.headers["location"] == "/connections?connected=calendar"
    assert client.calendar.finished_with["code"] == "abc" and client.gmail.finished_with is None


def test_callback_still_sends_gmail_state_to_gmail(client):
    r = client.get("/api/oauth/callback?code=abc&state=gmail.xyz")
    assert r.headers["location"] == "/connections?connected=gmail"
    assert client.gmail.finished_with is not None and client.calendar.finished_with is None


def test_a_calendar_failure_does_not_stop_the_bank_sync(monkeypatch, tmp_path):
    from backend.app.connectors.google_oauth import GoogleAuthError
    from backend.app.routers import sync as sync_router
    from backend.app.sync.ingest import SyncResult

    class Connected:
        def __init__(self, *a, **kw):
            self.oauth = type("O", (), {"is_connected": staticmethod(lambda: True)})()

    def broken_calendar(*a, **kw):
        raise GoogleAuthError("Google returned HTTP 410: updatedMinTooLongAgo", status=410)

    cursors = {}
    monkeypatch.setattr(sync_router, "default_vault", lambda: None)
    monkeypatch.setattr(sync_router, "GmailConnector", lambda vault: type("G", (), {"oauth": type(
        "O", (), {"is_connected": staticmethod(lambda: False)})()})())
    monkeypatch.setattr(sync_router, "CalendarConnector", Connected)
    monkeypatch.setattr(sync_router, "sync_calendar", broken_calendar)
    monkeypatch.setattr(sync_router.bank_session, "current", lambda: object())
    monkeypatch.setattr(sync_router, "sync_bank", lambda *a: SyncResult(provider="bank", records=3))
    monkeypatch.setattr(sync_router, "_ledger", lambda: None)
    monkeypatch.setattr(sync_router, "_profile", lambda: None)
    monkeypatch.setattr(sync_router, "_state", lambda: type(
        "S", (), {"set_cursor": staticmethod(lambda p, c: cursors.__setitem__(p, c))})())

    results = sync_router.run_sync()
    assert [r.provider for r in results] == ["bank"] and cursors == {"calendar": None}  # 410 -> fresh backfill
