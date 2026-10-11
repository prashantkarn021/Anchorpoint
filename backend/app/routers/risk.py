"""POST /api/risk-check: the deterministic rules decide the verdict; the auditor agent only explains.

Checks an offered assignment against the evidence ledger and work history (plan §8 / M7).
The verdict comes from rule severities, never from the model (plan §9: any high -> high_risk,
any warn -> review_with_cpa, else go). explain() never raises: model off -> templated text.
"""

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, TypeAdapter

from backend.app.agents.auditor import explain
from backend.app.ledger import Ledger
from backend.app.models import Assignment, Finding, Profile, RiskReport
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
    offer_text: str | None = Field(default=None, max_length=MAX_OFFER_CHARS)
    assignment_id: str | None = None


def verdict(findings: list[Finding]) -> str:
    severities = {f.severity for f in findings}
    if "high" in severities:
        return "high_risk"
    if "warn" in severities:
        return "review_with_cpa"
    return "go"


def _pick_offer(body: RiskCheckRequest, assignments: list[Assignment]) -> Assignment:
    offered = [a for a in assignments if a.status == "offered"]
    if body.assignment_id:
        match = [a for a in offered if a.id == body.assignment_id]  # past work isn't an offer
        if not match:
            raise HTTPException(status_code=404, detail="Offered assignment not found")
        return match[0]
    # Pasted offer text: match it to a known offered assignment by facility or metro name.
    # ponytail: no free-text offer parsing yet; an offer must arrive as an assignment first
    text = (body.offer_text or "").lower()
    match = [a for a in offered if a.facility.lower() in text or a.metro.name.lower() in text]
    if not text or not match:
        raise HTTPException(status_code=422, detail="Choose an offered assignment to check")
    return match[0]


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
    return RiskReport(
        verdict=verdict(findings),
        findings=findings,
        narrative=explained.narrative,
        questions_for_cpa=explained.questions_for_cpa,
        generated_at=datetime.now(UTC),
        ai_explanation_available=explained.ai_explanation_available,
    )
