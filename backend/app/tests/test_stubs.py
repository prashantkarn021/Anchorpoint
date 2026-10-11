import json
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from backend.app.main import app
from backend.app.models import (
    Assessment,
    Assignment,
    MonthlyLedgerRow,
    Profile,
    Record,
)

client = TestClient(app)


def fixture_data(filename):
    path = Path(__file__).resolve().parents[3] / "contract" / "fixtures" / filename
    return json.loads(path.read_text(encoding="utf-8"))


def test_profile():
    response = client.get("/api/profile")
    assert response.status_code == 200
    profile = Profile.model_validate(response.json())
    assert profile.name == "Maya Torres"
    assert profile.home_metro.name == "Kansas City"
    assert profile.home_metro.state == "MO"
    assert profile.family_at_home


def test_records():
    response = client.get("/api/records")
    assert response.status_code == 200
    records = TypeAdapter(list[Record]).validate_python(response.json())
    assert Counter(item.type for item in records) == Counter(
        item["type"] for item in fixture_data("records.json")
    )
    assert len({item.id for item in records}) == len(fixture_data("records.json"))
    for item in records:
        assert item.source.source_id
        assert item.source.snippet
        assert item.source.content_hash
        assert item.history
        assert all(event.record_id == item.id for event in item.history)


def test_record():
    records = client.get("/api/records").json()
    response = client.get(f"/api/records/{records[0]['id']}")
    assert response.status_code == 200
    record = Record.model_validate(response.json())
    assert record.model_dump(mode="json") == records[0]
    assert client.get("/api/records/missing-record").status_code == 404


def test_assignments():
    response = client.get("/api/assignments")
    assert response.status_code == 200
    assignments = TypeAdapter(list[Assignment]).validate_python(response.json())
    assert Counter(item.status for item in assignments) == Counter(
        item["status"] for item in fixture_data("assignments.json")
    )
    record_ids = {item["id"] for item in client.get("/api/records").json()}
    assert all(set(item.source_record_ids) <= record_ids for item in assignments)


def test_assessment():
    response = client.get("/api/assessment")
    assert response.status_code == 200
    assessment = Assessment.model_validate(response.json())
    assert assessment.status == "needs_attention"
    assert len(assessment.findings) == len(fixture_data("assessment.json")["findings"])
    assert assessment.findings[0].rule_id == "R1"
    assert assessment.findings[0].severity == "warn"
    record_ids = {item["id"] for item in client.get("/api/records").json()}
    assert all(set(item.record_ids) <= record_ids for item in assessment.factors)
    assert set(assessment.findings[0].record_ids) <= record_ids


def test_ledger_monthly():
    response = client.get("/api/ledger/monthly")
    assert response.status_code == 200
    rows = TypeAdapter(list[MonthlyLedgerRow]).validate_python(response.json())
    assert [row.month for row in rows] == [
        row["month"] for row in fixture_data("ledger_monthly.json")
    ]
    assert [row.missing for row in rows if row.missing] == [["rent"]]
