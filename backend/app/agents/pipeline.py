"""Ingestion entry point for P2's sync: one non-bank RawItem -> optional CandidateRecord + AuditEvents.

triage -> (suspicious? log ignored_suspicious, stop) -> (irrelevant? log skipped, stop) -> extract. Never raises on model
trouble: a model error or an exhausted per-sync request budget becomes an event and the item is
retried next sync. The budget counts real model requests (every turn and retry) at the model
boundary, see llm.AkamaiModel.stream. Bank items never come here (P2 maps them without the LLM).
"""

import re
import unicodedata
from datetime import UTC, datetime

from pydantic import BaseModel

from backend.app.agents import extractor
from backend.app.agents.llm import MAX_REQUESTS_PER_SYNC, CallBudget, budget_exhausted
from backend.app.agents.prompts import item_text
from backend.app.agents.triage import triage
from backend.app.models import AuditEvent, CandidateRecord, Profile, RawItem

__all__ = ["MAX_REQUESTS_PER_SYNC", "CallBudget", "Ingested", "ingest", "looks_injected"]

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


def ingest(item: RawItem, profile: Profile, budget: CallBudget, *, use_cache: bool = True) -> Ingested:
    if item.provider == "bank":
        raise ValueError("bank items skip the LLM; map them in sync/")
    if looks_injected(item_text(item)):
        # free code check first: no model request, works even with the model down or no budget
        return Ingested(events=[_event(item, "ignored_suspicious", "instructions to an AI were ignored")])
    try:
        t = triage(item, budget) if use_cache else triage(item, budget, use_cache=False)
    except Exception as e:  # noqa: BLE001 - any model failure: log, retry next sync
        return _failed(item, "triage", e)

    if t.suspicious:
        return Ingested(events=[_event(item, "ignored_suspicious", "instructions to an AI were ignored")])
    if not t.relevant:
        # noise: no record, but one feed entry so the agent visibly skips it (plan §7)
        return Ingested(events=[_event(item, "skipped", "not tax-home evidence")])
    # ponytail: if the budget runs out here, this item's triage requests were spent for nothing;
    # it is re-triaged next sync (a triage cache would save that)
    try:
        if use_cache:
            candidate, cached = extractor.extract(item, profile, t.doc_type, budget)
        else:
            candidate, cached = extractor.extract(item, profile, t.doc_type, budget, use_cache=False)
    except Exception as e:  # noqa: BLE001
        return _failed(item, "extraction", e)
    return Ingested(candidate=candidate, cached=cached)


def _failed(item: RawItem, stage: str, e: Exception) -> Ingested:
    if budget_exhausted(e):
        return Ingested(events=[_event(item, "deferred_call_cap", "model request budget used up; retried next sync")])
    return Ingested(events=[_event(item, "model_error", f"{stage} failed ({type(e).__name__})")])
