from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.app.ledger import Ledger
from backend.app.main import app
from backend.app.models import AuditEvent
from backend.app.routers.activity import events_after, latest_id
from backend.app.routers.records import get_ledger


def add(ledger: Ledger, action: str, detail: str) -> None:
    ledger.add_event(AuditEvent(ts=datetime.now(UTC), actor="agent", action=action, detail=detail))


@pytest.fixture
def feed(tmp_path):
    ledger = Ledger(str(tmp_path / "activity.db"))
    app.dependency_overrides[get_ledger] = lambda: ledger
    yield TestClient(app), ledger
    app.dependency_overrides.clear()


def test_activity_lists_newest_first_in_the_contract_shape(feed):
    client, ledger = feed
    add(ledger, "found", "gmail: 3 new item(s) to read")
    add(ledger, "skipped", "gmail:m1: not evidence (Cedar & Thread)")
    add(ledger, "ignored_suspicious", "gmail:m2: instructions to an AI were ignored")

    events = client.get("/api/activity").json()

    assert [event["action"] for event in events] == ["ignored_suspicious", "skipped", "found"]
    assert set(events[0]) == {"ts", "actor", "action", "record_id", "detail"}
    assert events[0]["record_id"] is None


def test_activity_respects_the_limit(feed):
    client, ledger = feed
    for index in range(5):
        add(ledger, "found", f"event {index}")

    assert [e["detail"] for e in client.get("/api/activity?limit=2").json()] == ["event 4", "event 3"]
    assert client.get("/api/activity?limit=0").status_code == 422


def test_an_empty_ledger_has_an_empty_feed(feed):
    client, ledger = feed

    assert client.get("/api/activity").json() == []
    assert latest_id(ledger) == 0


def test_the_stream_helper_returns_only_newer_events_oldest_first(feed):
    _, ledger = feed
    add(ledger, "found", "first")
    start = latest_id(ledger)
    add(ledger, "skipped", "second")
    add(ledger, "extracted", "third")

    new = events_after(ledger, start)

    assert [event.detail for _, event in new] == ["second", "third"]
    assert [event_id for event_id, _ in new] == [start + 1, start + 2]
    assert events_after(ledger, new[-1][0]) == []
