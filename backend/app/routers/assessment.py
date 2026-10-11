"""The dashboard's numbers, computed from the ledger by the rules. Nothing here is a fixture."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import TypeAdapter

from backend.app import scoring
from backend.app.ledger import Ledger
from backend.app.models import Assessment, Assignment, MonthlyLedgerRow, Profile
from backend.app.routers.records import get_ledger
from backend.app.routers.stubs import load_fixture
from backend.app.rules.engine import load_rates

router = APIRouter(prefix="/api")


def profile() -> Profile:
    return load_fixture("profile.json", TypeAdapter(Profile))


def assignments() -> list[Assignment]:
    # ponytail: assignments are still the persona's fixture; deriving them from the
    # assignment-confirmation records is the next step.
    return load_fixture("assignments.json", TypeAdapter(list[Assignment]))


Records = Annotated[Ledger, Depends(get_ledger)]


@router.get("/assessment", response_model=Assessment)
def assessment(ledger: Records) -> Assessment:
    return scoring.assess(ledger.list_records(), assignments(), profile(), date.today(), load_rates())


@router.get("/ledger/monthly", response_model=list[MonthlyLedgerRow])
def ledger_monthly(ledger: Records) -> list[MonthlyLedgerRow]:
    return scoring.monthly_rows(ledger.list_records(), assignments(), date.today())
