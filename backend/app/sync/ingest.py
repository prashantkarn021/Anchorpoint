"""One sync run: connector -> (agents | bank mapper) -> ledger, with feed events.

Idempotent. Finished items are remembered, so a re-fetch costs no model requests, and the
provider cursor only moves once nothing is left waiting.
"""

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from pydantic import BaseModel

from backend.app.agents import pipeline
from backend.app.agents.llm import CallBudget
from backend.app.connectors.base import Connector
from backend.app.ledger import Ledger
from backend.app.models import AuditEvent, Profile, RawItem
from backend.app.sync.mapping import record_from_bank, record_from_candidate
from backend.app.sync.state import SyncState

WORKERS = 4  # the model allows 4 calls at once (llm.model_slot); more threads would only queue
WAITING = {"deferred_call_cap", "model_error"}

Ingest = Callable[[RawItem, Profile, CallBudget], pipeline.Ingested]


class SyncResult(BaseModel):
    provider: str
    fetched: int = 0
    new: int = 0
    records: int = 0
    skipped: int = 0
    suspicious: int = 0
    waiting: int = 0  # items the model could not get to; retried next sync


def _event(ledger: Ledger, action: str, detail: str, actor: str = "agent") -> None:
    ledger.add_event(AuditEvent(ts=datetime.now(UTC), actor=actor, action=action, detail=detail))


def _sender(item: RawItem) -> str:
    """Display name of the sender, reduced to plain characters. It is attacker-chosen text."""
    name = str(item.meta.get("from", "")).split("<")[0]
    return re.sub(r"[^A-Za-z0-9 &.\-]", "", name).strip()[:40] or "unknown sender"


def sync_gmail(
    connector: Connector,
    ledger: Ledger,
    state: SyncState,
    profile: Profile,
    budget: CallBudget | None = None,
    ingest: Ingest = pipeline.ingest,
) -> SyncResult:
    provider = connector.provider
    items, cursor = connector.fetch_since(state.cursor(provider))
    done = state.seen(provider)
    todo = [item for item in items if item.source_id not in done]
    result = SyncResult(provider=provider, fetched=len(items), new=len(todo))
    if todo:
        _event(ledger, "found", f"{provider}: {len(todo)} new item(s) to read", actor="system")

    budget = budget or CallBudget()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        outcomes = list(pool.map(lambda item: ingest(item, profile, budget), todo))

    waiting_reasons = set()
    for item, outcome in zip(todo, outcomes, strict=True):
        actions = {event.action for event in outcome.events}
        if actions & WAITING:
            # Not finished: leave it unmarked so the next sync tries again.
            result.waiting += 1
            waiting_reasons |= actions & WAITING
            continue
        for event in outcome.events:
            ledger.add_event(event)
        if outcome.candidate is not None:
            ledger.upsert_record(record_from_candidate(item, outcome.candidate))
            state.mark(provider, item.source_id, "record")
            result.records += 1
        elif "ignored_suspicious" in actions:
            state.mark(provider, item.source_id, "suspicious")
            result.suspicious += 1
        else:
            if "skipped" not in actions:  # the pipeline may already have said so
                _event(ledger, "skipped", f"{provider}:{item.source_id}: not evidence ({_sender(item)})")
            state.mark(provider, item.source_id, "skipped")
            result.skipped += 1

    note = None
    if result.waiting:
        # A dead model burns the budget on failed attempts, so an error outranks the cap.
        reason = "model unavailable" if "model_error" in waiting_reasons else "request budget used up"
        note = f"{provider}: {reason}"
        if state.note_changed(provider, note):
            _event(ledger, "deferred", f"{note}; {result.waiting} item(s) wait for the next sync")
    else:
        state.note_changed(provider, None)
        state.set_cursor(provider, cursor)
    state.set_last_sync(provider, datetime.now(UTC).isoformat())
    return result


def sync_bank(connector: Connector, ledger: Ledger, state: SyncState, profile: Profile) -> SyncResult:
    """Bank transactions never reach the model: a fixed descriptor table maps them."""
    items, cursor = connector.fetch_since(state.cursor("bank"))
    result = SyncResult(provider="bank", fetched=len(items), new=len(items))
    if items:
        _event(ledger, "found", f"bank: {len(items)} transaction(s) to read", actor="system")
    for item in items:
        record = record_from_bank(item, profile.home_metro.name)
        state.mark("bank", item.source_id, "record" if record else "skipped")
        if record is None:
            result.skipped += 1
            continue
        ledger.upsert_record(record)
        result.records += 1
    if result.skipped:
        _event(ledger, "skipped", f"bank: {result.skipped} everyday transaction(s) are not evidence")
    state.set_cursor("bank", cursor)
    state.set_last_sync("bank", datetime.now(UTC).isoformat())
    return result
