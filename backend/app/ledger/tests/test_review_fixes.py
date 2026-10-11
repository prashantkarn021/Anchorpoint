import json
from datetime import UTC, date, datetime

import pytest

from backend.app.ledger import Ledger
from backend.app.ledger.tests.test_ledger import record
from backend.app.models import AuditEvent


def test_resume_pages_return_every_event_once_in_ascending_order(tmp_path):
    ledger = Ledger(str(tmp_path / "events.db"))
    for index in range(5):
        ledger.add_event(AuditEvent(
            ts=datetime(2026, 9, 3, tzinfo=UTC), actor="agent", action="skipped",
            detail=f"Synthetic event {index}",
        ))

    cursor, received = 0, []
    while page := ledger.list_events(limit=2, after_id=cursor):
        ids = [event["id"] for event in page]
        assert ids == sorted(ids)
        received.extend(ids)
        cursor = ids[-1]

    assert received == [1, 2, 3, 4, 5]
    assert [event["id"] for event in ledger.list_events(limit=2)] == [5, 4]


@pytest.mark.parametrize("status", ["confirmed", "rejected"])
def test_resync_audits_previous_user_edited_values_and_survives_restart(tmp_path, status):
    path = str(tmp_path / "resync.db")
    ledger = Ledger(path)
    ledger.upsert_record(record())
    edits = {
        "amount": 1300.0, "payee": "Synthetic Corrected Payee", "address": "42 Fictional Avenue",
        "date": date(2026, 8, 5), "period_start": date(2026, 8, 1),
        "period_end": date(2026, 8, 31), "type": "utility_payment", "factor": 3,
    }
    edited = ledger.update_record("r1", user_status=status, edits=edits)
    before = edited.model_dump(mode="json")

    saved, created = ledger.upsert_record(record(content_hash="hash-2", amount=1200.0))

    assert not created
    assert saved.user_status == status
    assert saved.amount == 1200.0
    assert saved.history[:-1] == edited.history
    event = saved.history[-1]
    assert event.actor == "agent" and event.action == "edited"
    prefix = "Source content changed on re-sync. "
    assert event.detail.startswith(prefix)
    previous = json.loads(event.detail.removeprefix(prefix))["previous_values"]
    assert previous == {field: before[field] for field in edits}
    assert Ledger(path).get_record("r1") == saved
