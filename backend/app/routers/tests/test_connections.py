from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.app.agents.pipeline import Ingested
from backend.app.ledger import Ledger
from backend.app.main import app
from backend.app.models import AuditEvent, Metro, Profile, RawItem, Record
from backend.app.routers import connections, sync
from backend.app.routers.records import get_ledger
from backend.app.sync import bank_session
from backend.app.sync.ingest import sync_gmail
from backend.app.sync.state import SyncState


def record(provider: str, source_id: str) -> Record:
    return Record.model_validate({
        "id": f"{provider}-{source_id}", "type": "rent_payment", "factor": 2, "date": "2026-03-02",
        "amount": 1150.0, "extracted_by": "plaid" if provider == "bank" else "agent",
        "source": {"provider": provider, "source_id": source_id, "received_at": "2026-03-02T00:00:00Z",
                   "snippet": "rent", "content_hash": source_id},
    })


class FakePlaid:
    """Stands in for PlaidConnector: no network, counts what happened to it."""

    provider = "bank"

    def __init__(self, transactions):
        self.transactions = transactions
        self.items_created = 0
        self.revoked = False

    def start_auth(self):
        return "public-token"

    def finish_auth(self, params):
        self.items_created += 1

    def revoke(self):
        self.revoked = True


@pytest.fixture
def env(monkeypatch, tmp_path):
    """The connections routes on a throwaway ledger, no Gmail, no bank, background sync captured."""
    path = str(tmp_path / "connections.db")
    ledger, state = Ledger(path), SyncState(path)
    started = []
    monkeypatch.setattr(sync, "_state", lambda: state)
    monkeypatch.setattr(connections, "_gmail", lambda: None)
    monkeypatch.setattr(connections, "sync_in_background", lambda: started.append(True))
    monkeypatch.setattr(bank_session, "_connector", None)
    monkeypatch.setattr(bank_session, "_connected_at", None)
    monkeypatch.setattr(bank_session, "PlaidConnector", FakePlaid)
    app.dependency_overrides[get_ledger] = lambda: ledger
    yield TestClient(app), ledger, state, started
    app.dependency_overrides.clear()


def test_nothing_connected_lists_nothing(env):
    client, *_ = env

    assert client.get("/api/connections").json() == []


def test_connecting_the_bank_plants_the_persona_and_starts_a_sync(env):
    client, _, _, started = env

    response = client.post("/api/connections/bank/start", json={})

    assert response.status_code == 200
    assert response.json() == {"redirect_url": None, "link_token": None}
    planted = bank_session.current().transactions
    assert any(t["description"] == "WESTPORT PROPERTY MGMT ACH" for t in planted)
    assert started == [True]
    (bank,) = client.get("/api/connections").json()
    assert (bank["id"], bank["provider"], bank["status"]) == ("bank", "bank", "connected")


def test_reconnecting_the_bank_replaces_the_old_bank_records_only(env):
    client, ledger, state, _ = env
    ledger.upsert_record(record("bank", "old-item-txn"))
    ledger.upsert_record(record("gmail", "m1"))
    state.set_cursor("bank", "old-cursor")
    state.mark("bank", "old-item-txn", "record")

    client.post("/api/connections/bank/start", json={})

    assert [r.id for r in ledger.list_records()] == ["gmail-m1"]
    assert state.cursor("bank") is None
    assert state.seen("bank") == {}


def test_bank_connect_reports_an_unavailable_sandbox(env, monkeypatch):
    client, *_ = env

    def no_keys(transactions):
        raise KeyError("PLAID_CLIENT_ID")

    monkeypatch.setattr(bank_session, "PlaidConnector", no_keys)

    response = client.post("/api/connections/bank/start", json={})

    assert response.status_code == 503
    assert "PLAID" not in response.text
    assert client.get("/api/connections").json() == []


def test_connection_counts_come_from_the_ledger_and_sync_state(env):
    client, ledger, state, _ = env
    client.post("/api/connections/bank/start", json={})
    ledger.upsert_record(record("bank", "t1"))
    for source_id, outcome in (("t1", "record"), ("t2", "skipped"), ("t3", "skipped")):
        state.mark("bank", source_id, outcome)
    state.set_last_sync("bank", "2026-10-11T08:00:00+00:00")

    (bank,) = client.get("/api/connections").json()

    assert (bank["items_seen"], bank["records_created"]) == (3, 1)
    assert bank["last_sync"].startswith("2026-10-11T08:00:00")


def test_revoking_the_bank_removes_the_item_and_can_delete_its_data(env):
    client, ledger, _, _ = env
    client.post("/api/connections/bank/start", json={})
    connector = bank_session.current()
    ledger.upsert_record(record("bank", "t1"))
    ledger.upsert_record(record("gmail", "m1"))

    response = client.post("/api/connections/bank/revoke", json={"delete_data": True})

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["records_created"]) == ("revoked", 0)
    assert connector.revoked is True
    assert [r.id for r in ledger.list_records()] == ["gmail-m1"]
    assert client.get("/api/connections").json() == []


def test_revoking_something_not_connected_is_a_404(env):
    client, *_ = env

    assert client.post("/api/connections/bank/revoke", json={}).status_code == 404
    assert client.post("/api/connections/calendar/revoke", json={}).status_code == 404


def test_the_sync_does_not_repeat_a_skip_the_pipeline_already_logged(tmp_path):
    path = str(tmp_path / "skip.db")
    ledger, state = Ledger(path), SyncState(path)
    item = RawItem(provider="gmail", source_id="m1", received_at=datetime(2026, 3, 3, tzinfo=UTC),
                   text="promo", meta={"from": "Cedar & Thread <x@example.com>"})
    profile = Profile(id="p", name="Maya Torres", home_address="x",
                      home_metro=Metro(name="Kansas City", state="MO"), family_at_home=True)

    class Connector:
        provider = "gmail"

        def fetch_since(self, cursor):
            return [item], "1"

    def pipeline_that_logs_skips(item, profile, budget):
        return Ingested(events=[AuditEvent(ts=datetime.now(UTC), actor="agent", action="skipped",
                                           detail="gmail:m1: not relevant")])

    sync_gmail(Connector(), ledger, state, profile, ingest=pipeline_that_logs_skips)

    assert [event["action"] for event in ledger.list_events()].count("skipped") == 1
    assert state.seen("gmail") == {"m1": "skipped"}
