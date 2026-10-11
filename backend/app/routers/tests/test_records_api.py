from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.models import Record, SourceRef


def make_record(id="rent-1", **changes):
    values = {
        "id": id, "type": "rent_payment", "factor": 2, "date": date(2026, 9, 1),
        "amount": 1450.0, "payee": "Synthetic Property Management", "confidence": 0.9,
        "source": SourceRef(
            provider="gmail", source_id=f"source-{id}",
            received_at=datetime(2026, 9, 1, tzinfo=UTC),
            snippet="September rent payment received.", content_hash=f"hash-{id}",
        ),
        "extracted_by": "agent",
    }
    values.update(changes)
    return Record(**values)


@pytest.fixture
def ledger(tmp_path):
    from backend.app.ledger import Ledger

    return Ledger(str(tmp_path / "records.db"))


@pytest.fixture
def client(ledger):
    from backend.app.main import app
    from backend.app.routers.records import get_ledger

    app.dependency_overrides[get_ledger] = lambda: ledger
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_ledger, None)


@pytest.fixture
def persisted(ledger):
    record, _ = ledger.upsert_record(make_record())
    return record


def snapshot(ledger, id="rent-1"):
    return ledger.get_record(id).model_dump(mode="json")


def test_list_returns_persisted_records_and_empty_ledger(client, ledger):
    assert client.get("/api/records").json() == []
    first, _ = ledger.upsert_record(make_record())
    second, _ = ledger.upsert_record(make_record("utility-1", type="utility_bill"))
    response = client.get("/api/records")
    assert response.status_code == 200
    assert {row["id"] for row in response.json()} == {first.id, second.id}
    assert all(row["source"]["source_id"] and row["history"] for row in response.json())


@pytest.mark.parametrize("params", [
    {"type": "rent_payment"}, {"factor": 2}, {"status": "confirmed"},
    {"provider": "gmail"},
    {"type": "rent_payment", "factor": 2, "status": "confirmed", "provider": "gmail"},
])
def test_each_filter_and_combined_filters(client, ledger, params):
    ledger.upsert_record(make_record(user_status="confirmed"))
    ledger.upsert_record(make_record(
        "other-1", type="trip_home", factor=3,
        source=make_record("other-1").source.model_copy(update={"provider": "bank"}),
    ))
    response = client.get("/api/records", params=params)
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ["rent-1"]


@pytest.mark.parametrize("params", [
    {"type": "unknown"}, {"factor": 0}, {"factor": 4}, {"factor": "bad"},
    {"status": "unknown"}, {"provider": "unknown"},
])
def test_invalid_filter_returns_422(client, params):
    assert client.get("/api/records", params=params).status_code == 422


def test_get_record_returns_persisted_history_in_time_order(client, ledger, persisted):
    ledger.update_record(persisted.id, user_status="confirmed")
    ledger.update_record(persisted.id, edits={"amount": 1500.0})
    response = client.get(f"/api/records/{persisted.id}")
    assert response.status_code == 200
    assert response.json() == snapshot(ledger)
    history = response.json()["history"]
    assert [event["action"] for event in history] == ["extracted", "confirmed", "edited"]
    times = [datetime.fromisoformat(event["ts"]) for event in history]
    assert times == sorted(times)


def test_unknown_record_returns_exact_404(client):
    response = client.get("/api/records/missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "Record not found"}


@pytest.mark.parametrize("status", ["confirmed", "rejected"])
def test_patch_status_persists_user_event(client, ledger, persisted, status):
    before = snapshot(ledger)
    response = client.patch(f"/api/records/{persisted.id}", json={"user_status": status})
    assert response.status_code == 200
    after = response.json()
    assert after["user_status"] == status
    assert after["history"][:-1] == before["history"]
    assert after["history"][-1]["actor"] == "user"
    assert after["history"][-1]["action"] == status
    assert after == client.get(f"/api/records/{persisted.id}").json() == snapshot(ledger)


def test_patch_edits_validates_real_types_and_persists_event(client, ledger, persisted):
    edits = {
        "amount": 1600.25, "payee": "Synthetic Housing", "address": "10 Example Street",
        "date": "2026-09-02", "period_start": "2026-09-01", "period_end": "2026-09-30",
        "type": "mortgage", "factor": 3,
    }
    before = snapshot(ledger)
    response = client.patch(f"/api/records/{persisted.id}", json={"edits": edits})
    assert response.status_code == 200
    after = response.json()
    assert all(after[key] == value for key, value in edits.items())
    assert after["history"][:-1] == before["history"]
    assert after["history"][-1]["actor"] == "user"
    assert after["history"][-1]["action"] == "edited"
    assert after == client.get(f"/api/records/{persisted.id}").json() == snapshot(ledger)


@pytest.mark.parametrize("body", [
    {"edits": {"unknown": "value"}}, {"unknown": "value"},
    {"edits": {"amount": "not-a-number"}}, {"edits": {"amount": "1600"}},
    {"edits": {"amount": True}}, {"edits": {"payee": 123}},
    {"edits": {"address": 123}}, {"edits": {"type": "unknown"}},
    {"edits": {"factor": 5}}, {"edits": {"factor": True}},
    {"edits": {"date": "2026-02-30"}}, {"edits": {"date": "bad-date"}},
    {"edits": {"period_start": "bad-date"}}, {"edits": {"period_end": "bad-date"}},
    {"user_status": "unknown"}, {"user_status": None}, {},
])
def test_invalid_patch_leaves_record_and_audit_storage_unchanged(client, ledger, persisted, body):
    before, events = snapshot(ledger), ledger.list_events()
    response = client.patch(f"/api/records/{persisted.id}", json=body)
    assert response.status_code == 422
    assert snapshot(ledger) == before
    assert ledger.list_events() == events


def test_patch_unknown_record_returns_404_without_event(client, ledger):
    events = ledger.list_events()
    response = client.patch("/api/records/missing", json={"user_status": "confirmed"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Record not found"}
    assert ledger.list_events() == events


def test_valid_status_plus_invalid_edit_is_atomic(client, ledger, persisted):
    before, events = snapshot(ledger), ledger.list_events()
    response = client.patch(f"/api/records/{persisted.id}", json={
        "user_status": "confirmed", "edits": {"amount": 1700.0, "factor": 5},
    })
    assert response.status_code == 422
    assert snapshot(ledger) == before
    assert ledger.list_events() == events


def test_status_and_edit_together_append_both_user_events(client, persisted):
    response = client.patch(f"/api/records/{persisted.id}", json={
        "user_status": "confirmed", "edits": {"amount": 1700.0},
    })
    assert response.status_code == 200
    assert response.json()["user_status"] == "confirmed"
    assert response.json()["amount"] == 1700.0
    events = response.json()["history"][len(persisted.history):]
    assert len(events) == 2
    assert {event["action"] for event in events} == {"confirmed", "edited"}
    assert all(event["actor"] == "user" for event in events)


@pytest.mark.parametrize("body", [
    {"user_status": "pending"}, {"edits": {"amount": 1450.0}}, {"edits": {}},
    {"user_status": "pending", "edits": {"amount": 1450.0}},
])
def test_no_op_patch_does_not_append_events(client, ledger, persisted, body):
    before, events = snapshot(ledger), ledger.list_events()
    response = client.patch(f"/api/records/{persisted.id}", json=body)
    assert response.status_code == 200
    assert response.json() == before == snapshot(ledger)
    assert ledger.list_events() == events


def test_null_factor_is_an_explicit_edit(client, persisted):
    response = client.patch(f"/api/records/{persisted.id}", json={"edits": {"factor": None}})
    assert response.status_code == 200
    assert response.json()["factor"] is None
    assert response.json()["history"][-1]["action"] == "edited"


def test_restart_keeps_edits_and_history(client, ledger, persisted):
    from backend.app.ledger import Ledger
    from backend.app.routers.records import get_ledger, router

    response = client.patch(f"/api/records/{persisted.id}", json={
        "user_status": "confirmed", "edits": {"amount": 1800.0},
    })
    assert response.status_code == 200
    new_ledger = Ledger(ledger.path)
    new_app = FastAPI()
    new_app.include_router(router)
    new_app.dependency_overrides[get_ledger] = lambda: new_ledger
    with TestClient(new_app) as restarted:
        restored = restarted.get(f"/api/records/{persisted.id}")
    assert restored.status_code == 200
    assert restored.json() == response.json() == snapshot(new_ledger)


@pytest.mark.parametrize("sqlite_url", [False, True])
def test_database_url_creates_parent_and_reuses_ledger(tmp_path, monkeypatch, sqlite_url):
    from backend.app.routers.records import get_ledger

    path = tmp_path / "missing" / "nested" / "records.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}" if sqlite_url else str(path))
    first = get_ledger()
    assert path.parent.is_dir()
    first.upsert_record(make_record())
    assert path.is_file()
    assert get_ledger() is first
    assert get_ledger().get_record("rent-1").amount == 1450.0


def test_database_path_defaults_to_backend_data(tmp_path, monkeypatch):
    from backend.app.routers.records import get_ledger

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    get_ledger().upsert_record(make_record())
    assert (tmp_path / "backend" / "data" / "anchorpoint.db").is_file()


@pytest.mark.parametrize("status", ["confirmed", "rejected"])
@pytest.mark.parametrize("changed_source", [False, True])
def test_resync_preserves_user_status(client, ledger, persisted, status, changed_source):
    response = client.patch(f"/api/records/{persisted.id}", json={"user_status": status})
    assert response.status_code == 200
    incoming = make_record()
    if changed_source:
        incoming.amount = 1550.0
        incoming.source.content_hash = "updated-source-hash"
    ledger.upsert_record(incoming)
    restored = client.get(f"/api/records/{persisted.id}").json()
    assert restored["user_status"] == status
    assert any(event["actor"] == "user" and event["action"] == status
               for event in restored["history"])
