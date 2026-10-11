from datetime import UTC, datetime

import pytest

from backend.app.agents import pipeline, triage
from backend.app.agents.llm import CallBudget
from backend.app.ledger import Ledger
from backend.app.models import Metro, Profile, RawItem
from backend.app.sync.ingest import sync_gmail
from backend.app.sync.state import SyncState


@pytest.mark.parametrize("agent_logs_skip", [True, False])
def test_skipped_item_has_one_event_and_is_not_reprocessed(tmp_path, monkeypatch, agent_logs_skip):
    item = RawItem(
        provider="gmail", source_id="promo-1", received_at=datetime(2026, 9, 1, tzinfo=UTC),
        text="30% off fictional jackets with code FALL30",
    )
    profile = Profile(
        id="demo", name="Synthetic worker", home_address="123 Fictional Lane",
        home_metro=Metro(name="Kansas City", state="MO"), family_at_home=True,
    )
    path = str(tmp_path / "sync.db")
    ledger, state = Ledger(path), SyncState(path)
    calls = []

    def verdict(item, budget):
        calls.append(item.source_id)
        return triage.TriageResult(relevant=False, confidence=0.95)

    monkeypatch.setattr(pipeline, "triage", verdict)

    class Connector:
        provider = "gmail"

        def fetch_since(self, cursor):
            return [item], "next-page"

    def ingest(item, profile, budget):
        if agent_logs_skip:
            return pipeline.ingest(item, profile, budget)
        calls.append(item.source_id)
        return pipeline.Ingested()

    result = sync_gmail(Connector(), ledger, state, profile, ingest=ingest)
    skipped = [event for event in ledger.list_events() if event["action"] == "skipped"]
    assert len(skipped) == 1
    assert (result.skipped, result.records, result.waiting) == (1, 0, 0)
    assert ledger.list_records() == []
    assert state.seen("gmail") == {"promo-1": "skipped"}
    assert state.cursor("gmail") == "next-page"
    assert "FALL30" not in skipped[0]["detail"]
    assert skipped[0]["actor"] == "agent"
    before = ledger.list_events()

    # New objects on the same file prove the processed marker survives a restart.
    restarted_ledger, restarted_state = Ledger(path), SyncState(path)
    second = sync_gmail(
        Connector(), restarted_ledger, restarted_state, profile, budget=CallBudget(0), ingest=ingest,
    )
    assert (second.new, second.skipped, second.records) == (0, 0, 0)
    assert calls == ["promo-1"]
    assert restarted_ledger.list_events() == before
