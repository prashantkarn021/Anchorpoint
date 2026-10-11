"""Receipt uploads -> guarded extraction -> pending evidence with source and audit history."""

import hashlib
import math
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, TypeAdapter

from backend.app.agents import pipeline
from backend.app.agents.llm import CallBudget
from backend.app.agents.prompts import MAX_DOC_CHARS
from backend.app.connectors import upload
from backend.app.ledger import Ledger
from backend.app.models import AuditEvent, Profile, RawItem, Record
from backend.app.routers.records import get_ledger
from backend.app.routers.stubs import load_fixture
from backend.app.sync.mapping import record_from_candidate

router = APIRouter(prefix="/api")
RECEIPT_TYPES = {"lodging_receipt", "meal_receipt", "fuel_receipt", "other_expense", "rent_payment", "utility_payment"}


class ReceiptUploadResult(BaseModel):
    records: list[Record]
    receipts: list[upload.ReceiptReadout]


def _event(ledger: Ledger, action: str, source_id: str, detail: str) -> None:
    ledger.add_event(AuditEvent(
        ts=datetime.now(UTC), actor="agent", action=action, detail=f"upload:{source_id}: {detail}",
    ))


@router.post("/documents", response_model=list[Record] | ReceiptUploadResult)
def documents(
    files: Annotated[list[UploadFile], File()],
    ledger: Annotated[Ledger, Depends(get_ledger)],
    include_text: Annotated[bool, Form()] = False,
) -> list[Record] | ReceiptUploadResult:
    if not 1 <= len(files) <= upload.MAX_FILES:
        raise HTTPException(422, "Upload 1 to 10 receipts at a time.")
    prepared = {}
    # Validate the whole batch before making model calls or writing evidence.
    for file in files:
        data = file.file.read(upload.MAX_BYTES + 1)
        source_id = hashlib.sha256(data).hexdigest()
        try:
            pages = upload.prepare(data, file.content_type or "")
        except upload.InvalidReceipt as error:
            raise HTTPException(422, str(error)) from None
        prepared[source_id] = pages

    profile = load_fixture("profile.json", TypeAdapter(Profile))
    budget = CallBudget()
    results = []
    readouts = []
    for source_id, pages in prepared.items():
        existing = ledger.get_record(f"upload-{source_id}")
        if existing is not None and not include_text:
            results.append(existing)
            continue
        _event(ledger, "found", source_id, "receipt received")
        try:
            text = "\n\n".join(
                page if isinstance(page, str) else upload.transcribe(page, budget) for page in pages
            )[:MAX_DOC_CHARS]
        except Exception:  # noqa: BLE001 - never expose model responses or credentials
            _event(ledger, "model_error", source_id, "receipt vision unavailable; no record created")
            raise HTTPException(503, "Receipt reading is unavailable. Images need a vision-capable inference model; retry later.") from None
        if not text.strip():
            _event(ledger, "skipped", source_id, "no readable receipt text")
            readouts.append(upload.ReceiptReadout(source_id=source_id, text=text, status="unreadable",
                                                 messages=["No receipt text could be read. Try a clearer picture."]))
            if existing is not None:
                results.append(existing)
            continue
        item = RawItem(provider="upload", source_id=source_id, received_at=datetime.now(UTC), text=text)
        outcome = pipeline.ingest(item, profile, budget, use_cache=False)
        for event in outcome.events:
            ledger.add_event(event)
        if any(event.action in {"model_error", "deferred_call_cap"} for event in outcome.events):
            raise HTTPException(503, "Receipt extraction is unavailable; retry later.")
        candidate = outcome.candidate
        if candidate is None:
            suspicious = any(event.action == "ignored_suspicious" for event in outcome.events)
            readouts.append(upload.ReceiptReadout(
                source_id=source_id, text=text, status="ignored_suspicious" if suspicious else "not_receipt",
                messages=["Instructions inside the image were ignored; no new record created." if suspicious
                          else "The text was not recognized as a supported receipt; no new record created."],
            ))
            if existing is not None:
                results.append(existing)
            continue
        if candidate.doc_type not in RECEIPT_TYPES:
            _event(ledger, "skipped", source_id, "document is not a supported receipt")
            readouts.append(upload.ReceiptReadout(source_id=source_id, text=text, status="not_receipt",
                                                 messages=["This document is not a supported receipt."]))
            if existing is not None:
                results.append(existing)
            continue
        if not math.isfinite(candidate.confidence) or (
            candidate.amount is not None and (not math.isfinite(candidate.amount) or candidate.amount < 0)
        ):
            _event(ledger, "model_error", source_id, "invalid extracted receipt fields; no record created")
            raise HTTPException(503, "Receipt fields could not be verified; retry with a clearer receipt.")
        readout = upload.check_receipt(source_id, text, candidate, ledger.list_records(), datetime.now(UTC).date())
        readouts.append(readout)
        _event(ledger, "receipt_checked", source_id, f"Basic receipt checks: {readout.status}; authenticity unverified.")
        if existing is not None:
            results.append(existing)  # Re-reading text never overwrites user edits or confirmation.
            continue
        record = record_from_candidate(item, candidate)
        updates = {"source": record.source.model_copy(update={"content_hash": source_id})}
        if candidate.dates:
            updates["date"] = candidate.dates[0]
        if any(isinstance(page, bytes) for page in pages) or (include_text and readout.status == "needs_review"):
            # A text quote can be checked against OCR, but not independently against the photo.
            updates.update(confidence=min(record.confidence, 0.69), needs_review=True)
        results.append(record.model_copy(update=updates))

    # A model failure in a later file leaves the entire batch's new records unsaved.
    records = [ledger.upsert_record(record)[0] for record in results]
    return ReceiptUploadResult(records=records, receipts=readouts) if include_text else records
