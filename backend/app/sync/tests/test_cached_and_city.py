"""Cached-extraction feed label (plan §7) and fuel-in-home-city from Plaid's location field."""

from datetime import UTC, datetime

import pytest

from backend.app.agents.pipeline import Ingested
from backend.app.ledger import Ledger
from backend.app.models import RawItem
from backend.app.sync.ingest import sync_gmail
from backend.app.sync.mapping import record_from_bank
from backend.app.sync.state import SyncState
from backend.app.sync.tests.test_sync import (
    PROFILE,
    FakeConnector,
    actions,
    email,
    rent,
)


@pytest.fixture
def store(tmp_path):
    path = str(tmp_path / "sync.db")
    return Ledger(path), SyncState(path)


def _agents(cached: dict[str, bool]):
    return lambda item, profile, budget: Ingested(candidate=rent(), cached=cached[item.source_id])


def test_cached_extractions_get_one_feed_line(store):
    ledger, state = store
    items = [email("m1", "Rent received"), email("m2", "Rent received"), email("m3", "Rent received")]
    result = sync_gmail(FakeConnector(items), ledger, state, PROFILE,
                        ingest=_agents({"m1": True, "m2": True, "m3": False}))
    assert (result.records, result.cached) == (3, 2)
    cached = [e for e in ledger.list_events(limit=50) if e["action"] == "cached"]
    assert len(cached) == 1 and "2 record(s) restored from cached extraction" in cached[0]["detail"]
    assert cached[0]["record_id"] is None


def test_no_cached_line_when_everything_was_live(store):
    ledger, state = store
    sync_gmail(FakeConnector([email("m1", "Rent received")]), ledger, state, PROFILE,
               ingest=_agents({"m1": False}))
    assert "cached" not in actions(ledger)


def _bank(merchant: str, city: str | None, amount: float = 47.12) -> RawItem:
    return RawItem(provider="bank", source_id="t1", received_at=datetime(2026, 5, 2, tzinfo=UTC),
                   text=f"2026-05-02  {merchant}  {amount:.2f} USD",
                   meta={"merchant": merchant, "amount": amount, "city": city})


def test_fuel_in_home_city_uses_plaids_location_city():
    # Plaid returns name "QUIKFUEL" and keeps "Kansas City" only in location.city
    assert record_from_bank(_bank("QUIKFUEL", "Kansas City"), "Kansas City").type == "trip_home"
    assert record_from_bank(_bank("QUIKFUEL", "Denver"), "Kansas City") is None  # fuel away from home
    assert record_from_bank(_bank("QUIKFUEL", None), "Kansas City") is None      # no location given
    # descriptor-only city still works, and unrelated merchants aren't promoted by the city
    assert record_from_bank(_bank("QUIKFUEL KANSAS CITY MO", None), "Kansas City").type == "trip_home"
    assert record_from_bank(_bank("PEAKSIDE GROCER", "Kansas City"), "Kansas City") is None


def test_city_never_turns_everyday_spending_into_evidence():
    # review: the city must only feed the fuel check, not BANK_RULES ("Brentwood" contains "RENT")
    for city in ("Brentwood", "Clearwater", "Airway Heights", "Innsbrook"):
        assert record_from_bank(_bank("PEAKSIDE COFFEE", city, 4.5), "Kansas City") is None, city
