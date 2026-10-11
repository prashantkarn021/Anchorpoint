import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier

import pytest

from backend.app.models import AuditEvent, Record, SourceRef


@pytest.fixture
def ledger(tmp_path):
    from backend.app.ledger import Ledger

    return Ledger(str(tmp_path / "ledger.sqlite3"))


def record(rid="r1", *, provider="gmail", source_id=None, content_hash="hash-1", **fields):
    return Record(
        **{
            "id": rid,
            "type": "rent_payment",
            "factor": 2,
            "date": date(2026, 9, 3),
            "amount": 1150.0,
            "payee": "Synthetic Property Management",
            "address": "1842 Fictional Lantern Lane",
            "source": SourceRef(
                provider=provider,
                source_id=source_id or f"source-{rid}",
                received_at=datetime(2026, 9, 3, tzinfo=UTC),
                snippet="Synthetic rent payment",
                content_hash=content_hash,
            ),
            "extracted_by": "agent",
            **fields,
        }
    )


@pytest.mark.parametrize("extracted_by,actor", [("agent", "agent"), ("plaid", "system"), ("user", "system")])
def test_new_upsert_creates_record_and_one_extracted_event(ledger, extracted_by, actor):
    incoming = record(extracted_by=extracted_by)

    saved, created = ledger.upsert_record(incoming)

    assert created is True
    assert saved.model_dump(exclude={"history"}) == incoming.model_dump(exclude={"history"})
    assert len(saved.history) == 1
    assert saved.history[0].actor == actor
    assert saved.history[0].action == "extracted"
    assert saved.history[0].record_id == incoming.id
    assert ledger.get_record(incoming.id) == saved
    assert len(ledger.list_events()) == 1


def test_same_hash_does_not_change_record_or_append_event(ledger):
    original, _ = ledger.upsert_record(record())

    saved, created = ledger.upsert_record(record("new-id", source_id="source-r1", amount=999.0))

    assert created is False
    assert saved == original
    assert ledger.get_record("new-id") is None
    assert len(ledger.list_records()) == 1
    assert len(ledger.list_events()) == 1


def test_changed_hash_updates_fields_and_keeps_id_and_confirmed_status(ledger):
    ledger.upsert_record(record())
    ledger.update_record("r1", user_status="confirmed")
    incoming = record("replacement", source_id="source-r1", content_hash="hash-2", amount=1200.0)

    saved, created = ledger.upsert_record(incoming)

    assert created is False
    assert saved.id == "r1"
    assert saved.user_status == "confirmed"
    assert saved.amount == 1200.0
    assert saved.source.content_hash == "hash-2"
    assert [event.action for event in saved.history] == ["extracted", "confirmed", "edited"]
    assert saved.history[-1].actor == "agent"
    assert ledger.get_record("replacement") is None


@pytest.mark.parametrize("status,action", [("confirmed", "confirmed"), ("rejected", "rejected")])
def test_user_status_update_appends_user_event(ledger, status, action):
    ledger.upsert_record(record())

    ledger.update_record("r1", user_status=status)

    saved = ledger.get_record("r1")
    assert saved.user_status == status
    assert [event.action for event in saved.history] == ["extracted", action]
    assert saved.history[-1].actor == "user"
    assert saved.history[-1].record_id == "r1"


def test_update_unknown_id_raises_key_error(ledger):
    with pytest.raises(KeyError):
        ledger.update_record("unknown", user_status="confirmed")
    assert ledger.get_record("unknown") is None
    assert ledger.list_events() == []


def test_user_edits_allowed_fields_and_appends_event(ledger):
    ledger.upsert_record(record())
    edits = {
        "amount": 1200.0,
        "payee": "Synthetic New Payee",
        "address": "42 Fictional Avenue",
        "date": date(2026, 8, 5),
        "period_start": date(2026, 8, 1),
        "period_end": date(2026, 8, 31),
        "type": "utility_payment",
        "factor": 3,
    }

    ledger.update_record("r1", edits=edits)

    saved = ledger.get_record("r1")
    assert all(getattr(saved, field) == value for field, value in edits.items())
    assert saved.source == record().source
    assert saved.history[-1].actor == "user"
    assert [event.action for event in saved.history] == ["extracted", "edited"]


@pytest.mark.parametrize("field,value", [("id", "replacement"), ("user_status", "confirmed"), ("confidence", 0.2)])
def test_user_edits_cannot_change_protected_fields(ledger, field, value):
    original, _ = ledger.upsert_record(record())

    with pytest.raises(ValueError):
        ledger.update_record("r1", edits={field: value})

    assert ledger.get_record("r1") == original
    assert len(ledger.list_events()) == 1


def test_get_record_assembles_history_in_time_order(ledger):
    ledger.upsert_record(record())
    ledger.update_record("r1", user_status="confirmed")
    ledger.update_record("r1", edits={"amount": 1200.0})

    history = ledger.get_record("r1").history

    assert [event.action for event in history] == ["extracted", "confirmed", "edited"]
    assert [event.ts for event in history] == sorted(event.ts for event in history)
    assert all(event.record_id == "r1" for event in history)


def test_record_json_excludes_history_and_reopening_preserves_audit(tmp_path, ledger):
    from backend.app.ledger import Ledger

    ledger.upsert_record(record())
    ledger.update_record("r1", user_status="confirmed")
    path = tmp_path / "ledger.sqlite3"

    with sqlite3.connect(path) as connection:
        stored = json.loads(connection.execute("SELECT json FROM records WHERE id = ?", ("r1",)).fetchone()[0])
        assert "history" not in stored
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    assert Ledger(str(path)).get_record("r1") == ledger.get_record("r1")


def test_list_records_filters_and_orders_by_date_descending_then_id(ledger):
    examples = [
        record("b", provider="bank", extracted_by="plaid", type="utility_payment", factor=3),
        record("a", user_status="confirmed"),
        record("old", date=date(2026, 8, 3), user_status="rejected"),
    ]
    for incoming in examples:
        ledger.upsert_record(incoming)

    def ids(**filters):
        return [item.id for item in ledger.list_records(**filters)]

    assert ids() == ["a", "b", "old"]
    assert ids(type="rent_payment") == ["a", "old"]
    assert ids(factor=3) == ["b"]
    assert ids(status="confirmed") == ["a"]
    assert ids(provider="bank") == ["b"]
    assert ids(type="rent_payment", factor=2, status="confirmed", provider="gmail") == ["a"]
    assert ids(type="mortgage") == []
    assert all(len(item.history) == 1 for item in ledger.list_records())


@pytest.mark.parametrize("content_hash", ["hash-1", "hash-2"])
def test_resync_does_not_unreject_record(ledger, content_hash):
    ledger.upsert_record(record())
    ledger.update_record("r1", user_status="rejected")

    saved, created = ledger.upsert_record(record(content_hash=content_hash))

    assert created is False
    assert saved.user_status == "rejected"
    assert ledger.get_record("r1").user_status == "rejected"
    assert len(saved.history) == (2 if content_hash == "hash-1" else 3)


def test_add_standalone_events_and_list_newest_first_with_resume_id(ledger):
    start = datetime(2026, 9, 3, tzinfo=UTC)
    for index, action in enumerate(("skipped", "ignored_suspicious", "skipped")):
        ledger.add_event(AuditEvent(ts=start + timedelta(seconds=index), actor="agent", action=action, detail=f"Synthetic item {index}"))

    # Event rows are flat dictionaries: row id plus the AuditEvent fields.
    events = ledger.list_events()

    assert [event["detail"] for event in events] == ["Synthetic item 2", "Synthetic item 1", "Synthetic item 0"]
    assert [event["id"] for event in events] == sorted((event["id"] for event in events), reverse=True)
    assert len({event["id"] for event in events}) == 3
    assert all(AuditEvent.model_validate(event).record_id is None for event in events)
    assert ledger.list_events(limit=2) == events[:2]
    assert ledger.list_events(after_id=events[1]["id"]) == events[:1]
    assert ledger.list_events(after_id=events[0]["id"]) == []
    assert ledger.list_records() == []


def test_source_key_includes_provider(ledger):
    ledger.upsert_record(record("gmail", source_id="shared"))
    _, created = ledger.upsert_record(record("bank", provider="bank", source_id="shared", extracted_by="plaid"))

    assert created is True
    assert len(ledger.list_records()) == 2


def test_two_threads_upsert_different_records_successfully(ledger):
    barrier = Barrier(2)

    def insert(rid):
        barrier.wait(timeout=10)
        return ledger.upsert_record(record(rid))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(insert, rid) for rid in ("r1", "r2")]
        results = [future.result(timeout=15) for future in futures]

    assert all(created for _, created in results)
    assert {saved.id for saved, _ in results} == {"r1", "r2"}
    assert {saved.id for saved in ledger.list_records()} == {"r1", "r2"}
    assert len(ledger.list_events()) == 2
