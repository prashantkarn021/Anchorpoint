from pathlib import Path
from typing import TypeVar

from fastapi import APIRouter, HTTPException
from pydantic import TypeAdapter

from backend.app.models import (
    Assessment,
    Assignment,
    Connection,
    MonthlyLedgerRow,
    Profile,
    Record,
)

router = APIRouter(prefix="/api")
FIXTURES = Path(__file__).resolve().parents[3] / "contract" / "fixtures"
T = TypeVar("T")


def load_fixture(filename: str, adapter: TypeAdapter[T]) -> T:
    return adapter.validate_json((FIXTURES / filename).read_text(encoding="utf-8"))


@router.get("/profile", response_model=Profile)
def profile() -> Profile:
    return load_fixture("profile.json", TypeAdapter(Profile))


@router.get("/connections", response_model=list[Connection])
def connections() -> list[Connection]:
    return load_fixture("connections.json", TypeAdapter(list[Connection]))


@router.get("/records", response_model=list[Record])
def records() -> list[Record]:
    return load_fixture("records.json", TypeAdapter(list[Record]))


@router.get("/records/{id}", response_model=Record)
def record(id: str) -> Record:
    for item in records():
        if item.id == id:
            return item
    raise HTTPException(status_code=404, detail="Record not found")


@router.get("/assignments", response_model=list[Assignment])
def assignments() -> list[Assignment]:
    return load_fixture("assignments.json", TypeAdapter(list[Assignment]))


@router.get("/assessment", response_model=Assessment)
def assessment() -> Assessment:
    return load_fixture("assessment.json", TypeAdapter(Assessment))


@router.get("/ledger/monthly", response_model=list[MonthlyLedgerRow])
def ledger_monthly() -> list[MonthlyLedgerRow]:
    return load_fixture("ledger_monthly.json", TypeAdapter(list[MonthlyLedgerRow]))
