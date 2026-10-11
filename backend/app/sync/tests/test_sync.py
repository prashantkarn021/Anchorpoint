from datetime import UTC, date, datetime

import pytest

from backend.app.agents.pipeline import Ingested
from backend.app.ledger import Ledger
from backend.app.models import AuditEvent, CandidateRecord, Metro, Profile, RawItem
from backend.app.sync.ingest import sync_bank, sync_gmail
from backend.app.sync.mapping import (
    bank_record_type,
    record_from_bank,
    record_from_candidate,
)
from backend.app.sync.state import SyncState

HOME = "1842 Fictional Lantern Lane, Unit 3, Kansas City, MO 64100"
PROFILE = Profile(
    id="maya-torres", name="Maya Torres", home_address=HOME,
    home_metro=Metro(name="Kansas City", state="MO"), family_at_home=True,
)


def email(source_id: str, subject: str, sender: str = "Westport Property Mgmt", hour: int = 15) -> RawItem:
    return RawItem(
        provider="gmail",
        source_id=source_id,
        received_at=datetime(2026, 3, 3, hour, 0, tzinfo=UTC),
        text=f"Subject: {subject}\n\nbody of {source_id}",
        meta={"from": f"{sender} <x@example.com>", "subject": subject, "snippet": f"snippet {source_id}",
              "deep_link": f"https://mail.google.com/mail/u/0/#all/{source_id}"},
    )


def rent(amount: float = 1150.0) -> CandidateRecord:
    return CandidateRecord(doc_type="rent_payment", payee="Westport Property Mgmt", address=HOME,
                           amount=amount, confidence=0.93, evidence_quote="We received your rent payment")


def agent_event(item: RawItem, action: str) -> AuditEvent:
    return AuditEvent(ts=datetime.now(UTC), actor="agent", action=action,
                      detail=f"{item.provider}:{item.source_id}: {action}")


class FakeConnector:
    provider = "gmail"

    def __init__(self, items, cursor="200"):
        self.items = items
        self.next_cursor = cursor
        self.cursors_asked = []

    def fetch_since(self, cursor):
        self.cursors_asked.append(cursor)
        return list(self.items), self.next_cursor


class FakeAgents:
    """Stands in for pipeline.ingest: outcome per source_id, and counts the calls."""

    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    def __call__(self, item, profile, budget):
        self.calls.append(item.source_id)
        outcome = self.outcomes[item.source_id]
        if outcome == "record":
            return Ingested(candidate=rent())
        if outcome == "noise":
            return Ingested()
        return Ingested(events=[agent_event(item, outcome)])


@pytest.fixture
def store(tmp_path):
    path = str(tmp_path / "sync.db")
    return Ledger(path), SyncState(path)


def actions(ledger: Ledger) -> list[str]:
    return [event["action"] for event in reversed(ledger.list_events())]


def test_evidence_becomes_a_pending_record_with_its_source(store):
    ledger, state = store
    connector = FakeConnector([email("m1", "Payment received - March 2026 rent")])

    result = sync_gmail(connector, ledger, state, PROFILE, ingest=FakeAgents({"m1": "record"}))

    (record,) = ledger.list_records()
    assert (result.records, result.new, result.waiting) == (1, 1, 0)
    assert record.id == "gmail-m1"
    assert (record.type, record.factor, record.user_status) == ("rent_payment", 2, "pending")
    assert record.date == date(2026, 3, 3)
    assert record.address == HOME
    assert record.source.source_id == "m1"
    assert record.source.deep_link.endswith("/m1")
    assert record.source.snippet == "We received your rent payment"
    assert record.extracted_by == "agent"
    assert [event.action for event in record.history] == ["extracted"]


def test_noise_and_suspicious_items_leave_events_but_no_records(store):
    ledger, state = store
    connector = FakeConnector([
        email("m1", "20% off scrubs", sender="Cedar & Thread;{}"),
        email("m2", "Action required", sender="Records Compliance"),
    ])

    result = sync_gmail(connector, ledger, state, PROFILE,
                        ingest=FakeAgents({"m1": "noise", "m2": "ignored_suspicious"}))

    assert ledger.list_records() == []
    assert (result.skipped, result.suspicious) == (1, 1)
    assert actions(ledger) == ["found", "skipped", "ignored_suspicious"]
    skipped = next(e for e in ledger.list_events() if e["action"] == "skipped")
    assert skipped["detail"] == "gmail:m1: not evidence (Cedar & Thread)"


def test_finished_items_are_not_sent_to_the_agents_again(store):
    ledger, state = store
    connector = FakeConnector([email("m1", "rent"), email("m2", "promo")])
    agents = FakeAgents({"m1": "record", "m2": "noise"})

    sync_gmail(connector, ledger, state, PROFILE, ingest=agents)
    second = sync_gmail(connector, ledger, state, PROFILE, ingest=agents)

    assert sorted(agents.calls) == ["m1", "m2"]
    assert (second.fetched, second.new, second.records) == (2, 0, 0)
    assert len(ledger.list_records()) == 1
    assert connector.cursors_asked == [None, "200"]


def test_items_the_model_could_not_reach_wait_and_hold_the_cursor(store):
    ledger, state = store
    connector = FakeConnector([email("m1", "rent"), email("m2", "bill"), email("m3", "bill")])
    agents = FakeAgents({"m1": "record", "m2": "deferred_call_cap", "m3": "deferred_call_cap"})

    first = sync_gmail(connector, ledger, state, PROFILE, ingest=agents)

    assert (first.records, first.waiting) == (1, 2)
    assert state.cursor("gmail") is None
    assert actions(ledger).count("deferred") == 1

    agents.outcomes.update({"m2": "record", "m3": "noise"})
    second = sync_gmail(connector, ledger, state, PROFILE, ingest=agents)

    assert sorted(agents.calls) == ["m1", "m2", "m2", "m3", "m3"]
    assert (second.records, second.skipped, second.waiting) == (1, 1, 0)
    assert state.cursor("gmail") == "200"


def test_a_model_outage_is_reported_once_not_on_every_poll(store):
    ledger, state = store
    connector = FakeConnector([email("m1", "rent")])
    agents = FakeAgents({"m1": "model_error"})

    for _ in range(3):
        sync_gmail(connector, ledger, state, PROFILE, ingest=agents)

    deferred = [e for e in ledger.list_events() if e["action"] == "deferred"]
    assert len(deferred) == 1
    assert "model unavailable" in deferred[0]["detail"]
    assert ledger.list_records() == []


def test_a_late_evening_email_is_dated_in_the_home_time_zone():
    item = email("m1", "rent", hour=3)  # 03:00 UTC is 22:00 the previous day in US Central

    assert record_from_candidate(item, rent()).date == date(2026, 3, 2)


def test_low_confidence_extractions_are_flagged_for_review():
    candidate = rent().model_copy(update={"confidence": 0.4})

    assert record_from_candidate(email("m1", "rent"), candidate).needs_review is True


@pytest.mark.parametrize(("merchant", "expected"), [
    ("WESTPORT PROPERTY MGMT ACH", "rent_payment"),
    ("STAYLOCAL FURNISHED RENTALS", "lodging_receipt"),
    ("EVERGREEN POWER & LIGHT AUTOPAY", "utility_payment"),
    ("PLAINSNET INTERNET", "utility_payment"),
    ("SKYLINE AIR", "trip_home"),
    ("QUIKFUEL KANSAS CITY MO", "trip_home"),
    ("PRAIRIE STATE MORTGAGE", "mortgage"),
    ("PEAKSIDE GROCER KANSAS CITY", None),
    ("QUIKFUEL DENVER CO", None),
    ("BLUE KETTLE COFFEE DENVER", None),
    ("IRONWORKS GYM KC", None),
])
def test_bank_descriptors_map_to_evidence_types(merchant, expected):
    assert bank_record_type(merchant, "Kansas City") == expected


def bank_item(source_id: str, merchant: str, amount: float) -> RawItem:
    return RawItem(provider="bank", source_id=source_id,
                   received_at=datetime(2026, 5, 2, tzinfo=UTC),
                   text=f"2026-05-02  {merchant}  {abs(amount):.2f} USD",
                   meta={"merchant": merchant, "amount": amount})


def test_bank_record_keeps_the_descriptor_and_ignores_deposits():
    record = record_from_bank(bank_item("t1", "WESTPORT PROPERTY MGMT ACH", 1150.0))

    assert (record.id, record.type, record.factor, record.amount) == ("bank-t1", "rent_payment", 2, 1150.0)
    assert (record.payee, record.address, record.extracted_by) == ("WESTPORT PROPERTY MGMT ACH", None, "plaid")
    assert record.date == date(2026, 5, 2)
    assert record_from_bank(bank_item("t2", "NORTHBRIDGE STAFFING STIPEND", -1505.0)) is None


def test_bank_sync_files_evidence_and_skips_everyday_spending(store):
    ledger, state = store
    connector = FakeConnector([
        bank_item("t1", "WESTPORT PROPERTY MGMT ACH", 1150.0),
        bank_item("t2", "BLUE KETTLE COFFEE DENVER", 5.25),
        bank_item("t3", "QUIKFUEL KANSAS CITY MO", 41.0),
    ], cursor="plaid-cursor")

    result = sync_bank(connector, ledger, state, PROFILE)
    again = sync_bank(connector, ledger, state, PROFILE)

    assert (result.records, result.skipped) == (2, 1)
    assert sorted(record.type for record in ledger.list_records()) == ["rent_payment", "trip_home"]
    assert state.cursor("bank") == "plaid-cursor"
    assert len(ledger.list_records()) == 2
    assert again.records == 2


def test_state_can_be_cleared_for_a_demo_reset(store):
    _, state = store
    state.set_cursor("gmail", "200")
    state.mark("gmail", "m1", "record")

    state.clear()

    assert state.cursor("gmail") is None
    assert state.seen("gmail") == {}
