import os
from datetime import date as Date
from functools import cache
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    TypeAdapter,
    model_validator,
)

from backend.app.ledger import Ledger
from backend.app.models import Provider, Record, RecordType

router = APIRouter(prefix="/api")
Status = Literal["confirmed", "rejected", "pending"]
Factor = Annotated[int, Field(strict=True, ge=1, le=3)]
_ledger_lock = Lock()


@cache
def _ledger_for_path(path: str) -> Ledger:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(path)
    if os.getenv("SEED_FIXTURES", "1") == "1" and not ledger.list_records():
        fixtures = Path(__file__).resolve().parents[3] / "contract" / "fixtures" / "records.json"
        for item in TypeAdapter(list[Record]).validate_json(fixtures.read_text(encoding="utf-8")):
            ledger.upsert_record(item)
    return ledger


def get_ledger() -> Ledger:
    path = os.getenv("DATABASE_URL", "backend/data/anchorpoint.db")
    path = path.removeprefix("sqlite:///")
    with _ledger_lock:
        return _ledger_for_path(str(Path(path).resolve()))


class RecordEdits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: StrictFloat | None = None
    payee: Annotated[str, Field(strict=True)] | None = None
    address: Annotated[str, Field(strict=True)] | None = None
    date: Date = None
    period_start: Date | None = None
    period_end: Date | None = None
    type: RecordType = None
    factor: Factor | None = None


class RecordPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_status: Status = None
    edits: RecordEdits = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("Provide user_status or edits")
        return self


@router.get("/records", response_model=list[Record])
def records(
    ledger: Annotated[Ledger, Depends(get_ledger)],
    type: RecordType | None = None,
    factor: Annotated[int | None, Field(ge=1, le=3)] = None,
    status: Status | None = None,
    provider: Provider | None = None,
) -> list[Record]:
    return ledger.list_records(type=type, factor=factor, status=status, provider=provider)


@router.get("/records/{id}", response_model=Record)
def record(id: str, ledger: Annotated[Ledger, Depends(get_ledger)]) -> Record:
    result = ledger.get_record(id)
    if result is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return result


@router.patch("/records/{id}", response_model=Record)
def patch_record(id: str, body: RecordPatch, ledger: Annotated[Ledger, Depends(get_ledger)]) -> Record:
    edits = body.edits.model_dump(exclude_unset=True) if body.edits is not None else {}
    try:
        return ledger.update_record(id, user_status=body.user_status, edits=edits)
    except KeyError:
        raise HTTPException(status_code=404, detail="Record not found") from None
