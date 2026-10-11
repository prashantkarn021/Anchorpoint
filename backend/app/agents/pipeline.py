"""Ingestion entry point for P2's sync: one non-bank RawItem -> optional CandidateRecord + AuditEvents.

triage -> (suspicious? log ignored_suspicious, stop) -> (relevant? extract). Never raises on model
trouble: a model error or an exhausted per-sync call budget becomes an event and the item is
retried next sync. Bank items never come here (P2 maps them without the LLM).
"""

import re
import threading
import unicodedata
from datetime import UTC, datetime

from pydantic import BaseModel

from backend.app.agents import extractor
from backend.app.agents.prompts import item_text
from backend.app.agents.triage import triage
from backend.app.models import AuditEvent, CandidateRecord, Profile, RawItem

MAX_CALLS_PER_SYNC = 40

# Code backstop: obvious instructions to an AI are suspicious even if the model missed them.
# ponytail: keyword list, the triage model is the main detector
_INJECTION = re.compile(
    r"(ignore|disregard|forget) (all |any )?(the |your )?(previous|prior|above|earlier) instructions"
    r"|(note|message|attention) to (the |any )?(ai|assistant|automated)"
    r"|(ai|automated) assistant (processing|reading)"
    r"|mark (every|all) records?( in the ledger)? as confirmed"
    r"|forward (the |your )?(complete )?ledger",
    re.IGNORECASE,
)


class CallBudget:
    """Model calls allowed in one sync; create one per sync. Thread-safe."""

    def __init__(self, max_calls: int = MAX_CALLS_PER_SYNC):
        self.left = max_calls
        self._lock = threading.Lock()

    def take(self, n: int = 1) -> bool:
        with self._lock:
            if self.left < n:
                return False
            self.left -= n
            return True

    def refund(self, n: int = 1) -> None:
        with self._lock:
            self.left += n


class Ingested(BaseModel):
    candidate: CandidateRecord | None = None
    cached: bool = False
    events: list[AuditEvent] = []


def looks_injected(text: str) -> bool:
    # fold full-width/lookalike letters, drop zero-width/format chars, collapse whitespace
    text = "".join(c for c in unicodedata.normalize("NFKC", text) if unicodedata.category(c) != "Cf")
    return bool(_INJECTION.search(" ".join(text.split())))


def _event(item: RawItem, action: str, detail: str) -> AuditEvent:
    # detail never quotes the item's text: it's attacker-controlled
    return AuditEvent(ts=datetime.now(UTC), actor="agent", action=action,
                      detail=f"{item.provider}:{item.source_id}: {detail}")


def ingest(item: RawItem, profile: Profile, budget: CallBudget) -> Ingested:
    if item.provider == "bank":
        raise ValueError("bank items skip the LLM; map them in sync/")
    ignored = Ingested(events=[_event(item, "ignored_suspicious", "instructions to an AI were ignored")])
    if looks_injected(item_text(item)):
        return ignored  # free code check first: no model call, works even with the model down
    # reserve triage + extraction up front so a triaged item is never left without its extraction
    if not budget.take(2):
        return Ingested(events=[_event(item, "deferred_call_cap", "call budget used up; retried next sync")])
    try:
        t = triage(item)
    except Exception as e:  # noqa: BLE001 - any model failure: log, retry next sync
        budget.refund()
        return Ingested(events=[_event(item, "model_error", f"triage failed ({type(e).__name__})")])

    if t.suspicious:
        budget.refund()
        return ignored
    if not t.relevant:
        budget.refund()
        return Ingested()  # noise: no record, no feed entry
    if extractor.is_cached(item, profile, t.doc_type):
        budget.refund()
    try:
        candidate, cached = extractor.extract(item, profile, t.doc_type)
    except Exception as e:  # noqa: BLE001
        return Ingested(events=[_event(item, "model_error", f"extraction failed ({type(e).__name__})")])
    return Ingested(candidate=candidate, cached=cached)
