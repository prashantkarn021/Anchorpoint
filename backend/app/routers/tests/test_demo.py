import sqlite3

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.connectors.google_oauth import GoogleAuthError
from backend.app.ledger import Ledger
from backend.app.main import app
from backend.app.models import Record
from backend.app.routers import demo, sync
from backend.app.routers.demo import inbox_address, inject_writer
from backend.app.routers.records import get_ledger
from backend.app.sync.state import SyncState


class FakeWriter:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.inserted = []

    def insert(self, email, to_name, to_address) -> str:
        if self.fail:
            raise GoogleAuthError("Gmail returned HTTP 403: insufficient scope")
        self.inserted.append((email, to_name, to_address))
        return f"msg-{len(self.inserted)}"


@pytest.fixture
def client():
    def use(writer):
        app.dependency_overrides[inject_writer] = lambda: writer
        app.dependency_overrides[inbox_address] = lambda: "maya@example.com"
        return TestClient(app)

    yield use
    app.dependency_overrides.clear()


def test_inject_inserts_a_fresh_utility_bill_for_the_demo_persona(client):
    writer = FakeWriter()

    response = client(writer).post("/api/demo/inject")

    assert response.status_code == 200
    body = response.json()
    assert body["inserted"] == 1
    assert body["emails"][0]["source_id"] == "msg-1"
    assert body["emails"][0]["from"] == "Evergreen Power & Light"
    email, to_name, to_address = writer.inserted[0]
    assert (to_name, to_address) == ("Maya Torres", "maya@example.com")
    assert "1842 Fictional Lantern Lane" in email.body


def test_inject_reports_a_gmail_failure_without_details(client):
    response = client(FakeWriter(fail=True)).post("/api/demo/inject")

    assert response.status_code == 502
    assert "scope" not in response.json()["detail"]


def test_inject_is_unavailable_until_the_injector_is_granted(monkeypatch, tmp_path):
    monkeypatch.setenv("SEED_GOOGLE_CLIENT_ID", "seed-client")
    monkeypatch.setenv("SEED_GOOGLE_CLIENT_SECRET", "seed-secret")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'demo.db'}")
    monkeypatch.setenv("TOKEN_ENC_KEY", Fernet.generate_key().decode())
    demo.default_vault.cache_clear()

    with pytest.raises(HTTPException) as raised:
        inject_writer()

    demo.default_vault.cache_clear()
    assert raised.value.status_code == 503
    assert "not been granted" in raised.value.detail


def test_inject_is_unavailable_without_the_seeder_client(monkeypatch):
    monkeypatch.delenv("SEED_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("SEED_GOOGLE_CLIENT_SECRET", raising=False)

    with pytest.raises(HTTPException) as raised:
        inject_writer()

    assert raised.value.status_code == 503
    assert "SEED_GOOGLE_CLIENT_ID" in raised.value.detail


RECORD = {
    "id": "gmail-m1", "type": "rent_payment", "factor": 2, "date": "2026-03-03", "amount": 1150.0,
    "source": {"provider": "gmail", "source_id": "m1", "received_at": "2026-03-03T15:00:00Z",
               "snippet": "We received your rent payment", "content_hash": "abc"},
    "extracted_by": "agent",
}


@pytest.fixture
def reset_client(monkeypatch, tmp_path):
    """The reset route on a throwaway ledger and sync state, with the follow-up sync captured."""
    path = str(tmp_path / "reset.db")
    ledger, state = Ledger(path), SyncState(path)
    ledger.upsert_record(Record.model_validate(RECORD))
    state.set_cursor("gmail", "200")
    state.mark("gmail", "m1", "record")
    started = []
    monkeypatch.setattr(sync, "_state", lambda: state)
    monkeypatch.setattr(demo, "_sync_in_background", lambda bank=None: started.append(bank))
    app.dependency_overrides[get_ledger] = lambda: ledger
    yield TestClient(app), ledger, state, started
    app.dependency_overrides.clear()


def test_reset_empties_the_ledger_and_sync_memory_then_starts_a_sync(reset_client, monkeypatch):
    client, ledger, state, started = reset_client
    monkeypatch.setenv("SEED_FIXTURES", "0")

    response = client.post("/api/demo/reset", json={"persona": "maya"})

    assert response.status_code == 200
    assert response.json() == {
        "cleared": {"records": 1, "events": 1}, "fixtures_loaded": 0, "sync": "started",
    }
    assert ledger.list_records() == []
    assert ledger.list_events() == []
    assert state.cursor("gmail") is None
    assert state.seen("gmail") == {}
    assert started == [None]  # no bank connected, so nothing to re-create


def test_reset_reloads_fixture_records_when_seeding_is_on(reset_client, monkeypatch):
    client, ledger, _, _ = reset_client
    monkeypatch.setenv("SEED_FIXTURES", "1")

    response = client.post("/api/demo/reset", json={})

    assert response.json()["fixtures_loaded"] > 0
    assert len(ledger.list_records()) == response.json()["fixtures_loaded"]
    assert all(record.id != "gmail-m1" for record in ledger.list_records())


def test_reset_keeps_connections(reset_client):
    client, ledger, _, _ = reset_client
    with sqlite3.connect(ledger.path) as connection:
        connection.execute("CREATE TABLE vault_tokens (key TEXT PRIMARY KEY, value BLOB NOT NULL)")
        connection.execute("INSERT INTO vault_tokens VALUES ('gmail:tokens', x'00')")

    client.post("/api/demo/reset")

    with sqlite3.connect(ledger.path) as connection:
        assert connection.execute("SELECT count(*) FROM vault_tokens").fetchone()[0] == 1


def test_reset_waits_its_turn_when_a_sync_is_running(reset_client, monkeypatch):
    client, ledger, _, started = reset_client
    monkeypatch.setattr(sync, "WAIT_FOR_RUNNING_SYNC_S", 0.05)

    with sync.paused():
        response = client.post("/api/demo/reset")

    assert response.status_code == 409
    assert len(ledger.list_records()) == 1
    assert started == []
