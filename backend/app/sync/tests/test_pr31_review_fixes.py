"""Regression checks for PR #31's location evidence and extraction-cache label."""

from datetime import date
from types import SimpleNamespace

import pytest

from backend.app.agents import pipeline
from backend.app.agents.llm import CallBudget
from backend.app.connectors.plaid import to_raw_item
from backend.app.ledger import Ledger
from backend.app.sync.ingest import sync_gmail
from backend.app.sync.mapping import bank_record_type, record_from_bank
from backend.app.sync.state import SyncState
from backend.app.sync.tests.test_sync import PROFILE, FakeConnector, email, rent


@pytest.mark.parametrize("merchant,city", [
    ("QUIKFUEL", "North Kansas City"),
    ("QUIKFUEL", "Kansas Cityville"),
    ("QUIKFUEL KANSAS CITY MO", "Denver"),
])
def test_structured_location_must_match_the_home_city(merchant, city):
    assert bank_record_type(merchant, "Kansas City", city) is None


def test_structured_location_normalizes_case_and_whitespace():
    assert bank_record_type("QUIKFUEL", " kansas   CITY ", " KANSAS city ") == "trip_home"


def test_descriptor_fallback_requires_city_word_boundaries():
    assert bank_record_type("QUIKFUEL KANSAS CITYVILLE MO", "Kansas City") is None
    assert bank_record_type("QUIKFUEL KANSAS CITY MO", "Kansas City") == "trip_home"


def transaction(city):
    return SimpleNamespace(
        transaction_id="synthetic-fuel", date=date(2026, 5, 2), name="QUIKFUEL",
        merchant_name="QUIKFUEL", amount=47.12, iso_currency_code="USD",
        account_id="synthetic-account", location=SimpleNamespace(city=city),
    )


def test_location_evidence_survives_ledger_storage(tmp_path):
    item = to_raw_item(transaction("Kansas City"))
    record = record_from_bank(item, "Kansas City")
    ledger = Ledger(str(tmp_path / "ledger.db"))
    ledger.upsert_record(record)

    stored = ledger.get_record(record.id)
    assert "Kansas City" in stored.source.snippet
    assert stored.source.content_hash != record_from_bank(
        to_raw_item(transaction("Denver")), "Denver",
    ).source.content_hash
    assert stored.history


def test_cached_label_does_not_claim_triage_avoided_a_model_call(tmp_path, monkeypatch):
    def triage(item, budget):
        assert budget.take()  # Simulate an uncached triage request; extraction is cached.
        return SimpleNamespace(relevant=True, suspicious=False, doc_type="rent_payment")

    monkeypatch.setattr(pipeline, "triage", triage)
    monkeypatch.setattr(pipeline.extractor, "extract", lambda *args: (rent(), True))
    path = str(tmp_path / "sync.db")
    ledger, state, budget = Ledger(path), SyncState(path), CallBudget()
    result = sync_gmail(FakeConnector([email("m1", "Rent received")]), ledger, state,
                        PROFILE, budget=budget)

    assert result.cached == 1
    assert budget.left == CallBudget().left - 1
    cached = [event for event in ledger.list_events() if event["action"] == "cached"]
    assert len(cached) == 1
    assert "no extraction model call" in cached[0]["detail"]
    assert "(no model call)" not in cached[0]["detail"]
