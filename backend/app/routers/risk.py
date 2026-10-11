"""POST /api/risk-check: the deterministic rules decide the verdict; the auditor agent only explains.

Checks an offered assignment against the evidence ledger and work history (plan §8 / M7).
The verdict comes from rule severities, never from the model (plan §9: any high -> high_risk,
any warn -> review_with_cpa, else go). explain() never raises: model off -> templated text.
"""

import re
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from backend.app.agents.auditor import explain
from backend.app.agents.pipeline import looks_injected
from backend.app.ledger import Ledger
from backend.app.models import Assignment, AuditEvent, Finding, Profile, RiskReport
from backend.app.routers.records import get_ledger
from backend.app.routers.stubs import load_fixture
from backend.app.rules.engine import (
    check_housing_continuity,
    check_one_year_clock,
    check_return_trips,
    check_stipend_ceiling,
    check_utility_continuity,
    load_rates,
)

router = APIRouter(prefix="/api")

MAX_OFFER_CHARS = 4000


class RiskCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_text: str | None = Field(default=None, max_length=MAX_OFFER_CHARS)
    assignment_id: str | None = None

    @model_validator(mode="after")
    def one_input(self):
        if bool(self.offer_text and self.offer_text.strip()) == bool(self.assignment_id and self.assignment_id.strip()):
            raise ValueError("Provide exactly one of offer_text or assignment_id")
        return self


def verdict(findings: list[Finding]) -> str:
    severities = {f.severity for f in findings}
    if "high" in severities:
        return "high_risk"
    if "warn" in severities:
        return "review_with_cpa"
    return "go"


def _offer_terms(text: str, offer: Assignment) -> Assignment:
    """Read explicit sample-offer labels, without a model or guessed tax facts.

    The known assignment supplies location and omitted terms. ISO dates, a duration in
    weeks, and daily/weekly stipends can override it for this preview only.
    """
    updates = {}
    try:
        for label in ("start", "end"):
            values = re.findall(rf"\b{label}\s*:\s*(\S+)", text, re.IGNORECASE)
            if values:
                if len(values) != 1:
                    raise ValueError("Repeated date")
                updates[label] = date.fromisoformat(values[0].rstrip(",.;"))
        weeks = re.findall(r"\b(\d+)\s+(?:more\s+)?weeks?\b", text, re.IGNORECASE)
        if "end" not in updates and weeks:
            if len(weeks) != 1 or not 1 <= int(weeks[0]) <= 520:
                raise ValueError("Invalid duration")
            updates["end"] = updates.get("start", offer.start) + timedelta(weeks=int(weeks[0]))
        money = r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)"
        for label, field in (("lodging stipend", "weekly_lodging_stipend"), ("m&ie stipend", "weekly_mie_stipend")):
            if re.search(rf"\b{label}\b", text, re.IGNORECASE):
                values = re.findall(rf"\b{label}\s*:?\s*\$?{money}\s*/\s*(week|day)\b", text, re.IGNORECASE)
                if len(values) != 1:
                    raise ValueError("Use one daily or weekly stipend")
                amount, unit = values[0]
                updates[field] = float(amount.replace(",", "")) * (7 if unit.lower() == "day" else 1)
        if updates.get("end", offer.end) < updates.get("start", offer.start):
            raise ValueError("End precedes start")
    except (ValueError, OverflowError):
        raise HTTPException(
            status_code=422, detail="Use valid Start/End dates (YYYY-MM-DD) and stipend amounts ($number/week or /day)",
        ) from None
    return Assignment.model_validate(offer.model_dump() | updates)


def _pick_offer(body: RiskCheckRequest, assignments: list[Assignment]) -> Assignment:
    offered = [a for a in assignments if a.status == "offered"]
    if body.assignment_id:
        match = [a for a in offered if a.id == body.assignment_id]  # past work isn't an offer
        if not match:
            raise HTTPException(status_code=404, detail="Offered assignment not found")
        return match[0]
    # Match the location to a known offer; parse explicit terms rather than ignoring them.
    text = body.offer_text or ""
    if looks_injected(text):
        raise HTTPException(status_code=422, detail="Remove instructions to an AI from the offer text")
    text = text.lower()
    match = [a for a in offered if a.facility.lower() in text or a.metro.name.lower() in text]
    if not text or len(match) != 1:
        raise HTTPException(status_code=422, detail="Choose an offered assignment to check")
    return _offer_terms(text, match[0])


@router.post("/risk-check", response_model=RiskReport)
def risk_check(body: RiskCheckRequest, ledger: Annotated[Ledger, Depends(get_ledger)]) -> RiskReport:
    assignments = load_fixture("assignments.json", TypeAdapter(list[Assignment]))
    profile = load_fixture("profile.json", TypeAdapter(Profile))
    offer = _pick_offer(body, assignments)
    history = [a for a in assignments if a.status in ("completed", "active")]
    records = [r for r in ledger.list_records() if r.user_status != "rejected"]  # plan §9
    today = date.today()

    findings = (
        check_housing_continuity(records, today)
        + check_utility_continuity(records, today, profile.home_address)
        + check_return_trips(records, history)
        + check_one_year_clock(history, today, offer)
        + check_stipend_ceiling([offer], load_rates())
    )
    explained = explain(findings)  # cites only real record/rule IDs, else template
    result = verdict(findings)
    ledger.add_event(AuditEvent(
        ts=datetime.now(UTC), actor="rules", action="risk_checked",
        detail=f"Contract risk check: {result} ({len(findings)} findings).",
    ))
    return RiskReport(
        verdict=result,
        findings=findings,
        narrative=explained.narrative,
        questions_for_cpa=explained.questions_for_cpa,
        generated_at=datetime.now(UTC),
        ai_explanation_available=explained.ai_explanation_available,
    )
