from pathlib import Path
from typing import TypeVar

from fastapi import APIRouter
from pydantic import TypeAdapter

from backend.app.models import (
    Assignment,
    Profile,
)

router = APIRouter(prefix="/api")
FIXTURES = Path(__file__).resolve().parents[3] / "contract" / "fixtures"
T = TypeVar("T")


def load_fixture(filename: str, adapter: TypeAdapter[T]) -> T:
    return adapter.validate_json((FIXTURES / filename).read_text(encoding="utf-8"))


@router.get("/profile", response_model=Profile)
def profile() -> Profile:
    return load_fixture("profile.json", TypeAdapter(Profile))


@router.get("/assignments", response_model=list[Assignment])
def assignments() -> list[Assignment]:
    return load_fixture("assignments.json", TypeAdapter(list[Assignment]))
