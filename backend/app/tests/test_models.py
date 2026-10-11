from datetime import UTC, datetime
from datetime import date as Date

import pytest
from pydantic import ValidationError

from backend.app import models


@pytest.fixture
def samples():
    now = datetime(2026, 10, 10, tzinfo=UTC)
    day = Date(2026, 10, 10)
    metro = models.Metro(name="Kansas City", state="MO")
    source = models.SourceRef(
        provider="upload", source_id="synthetic-source", received_at=now,
        snippet="Synthetic rent payment", content_hash="synthetic-hash",
    )
    audit = models.AuditEvent(
        ts=now, actor="user", action="created", record_id="record-1",
        detail="Created from synthetic receipt",
    )
    finding = models.Finding(
        rule_id="synthetic-rule", severity="info", title="Synthetic finding",
        detail="Synthetic evidence", recommended_action="Review evidence",
    )
    factor = models.FactorStatus(
        factor=1, label="Synthetic factor", score=1, met=True, record_ids=["record-1"],
    )
    attachment = models.Attachment(
        filename="receipt.txt", mime_type="text/plain", size_bytes=10,
    )
    instances = [
        metro,
        models.Profile(
            id="profile-1", name="Synthetic Worker", home_address="123 Example St",
            home_metro=metro, family_at_home=True,
        ),
        models.Connection(
            id="connection-1", provider="upload", status="connected", scopes=[],
            connected_at=now,
        ),
        source,
        audit,
        models.Record(
            id="record-1", type="rent_payment", factor=1, date=day,
            source=source, extracted_by="user", history=[audit],
        ),
        models.Assignment(
            id="assignment-1", facility="Synthetic Facility", metro=metro,
            start=day, end=Date(2026, 12, 31), status="active",
            weekly_taxable_wage=1000, weekly_lodging_stipend=500,
            weekly_mie_stipend=200,
        ),
        finding,
        factor,
        models.Assessment(
            score=1, status="needs_attention", factors_met=1,
            factors=[factor], findings=[finding],
        ),
        models.MonthlyLedgerRow(
            month="2026-10", home_housing_paid=1000, home_utilities_paid=100,
            stipends_received=700,
        ),
        models.RiskReport(
            verdict="review_with_cpa", findings=[finding], narrative="Synthetic report",
            questions_for_cpa=["Is more evidence needed?"], generated_at=now,
        ),
        attachment,
        models.RawItem(
            provider="upload", source_id="synthetic-source", received_at=now,
            text="Synthetic receipt", attachments=[attachment],
        ),
        models.CandidateRecord(doc_type="rent_payment", confidence=0.9, dates=[day]),
    ]
    return {type(instance): instance for instance in instances}


MODEL_TYPES = [
    models.Metro, models.Profile, models.Connection, models.SourceRef,
    models.AuditEvent, models.Record, models.Assignment, models.Finding,
    models.FactorStatus, models.Assessment, models.MonthlyLedgerRow,
    models.RiskReport, models.Attachment, models.RawItem, models.CandidateRecord,
]


@pytest.mark.parametrize("model", MODEL_TYPES)
def test_valid_sample_round_trips(model, samples):
    sample = samples[model]
    assert model.model_validate_json(sample.model_dump_json()) == sample


@pytest.mark.parametrize("model", MODEL_TYPES)
def test_required_field_is_rejected_when_missing(model, samples):
    data = samples[model].model_dump()
    field = next(name for name, info in model.model_fields.items() if info.is_required())
    del data[field]
    with pytest.raises(ValidationError) as exc:
        model.model_validate(data)
    assert any(error["loc"] == (field,) for error in exc.value.errors())


@pytest.mark.parametrize(("model", "field", "value"), [
    (models.Connection, "provider", "unknown"),
    (models.Connection, "status", "unknown"),
    (models.SourceRef, "provider", "unknown"),
    (models.AuditEvent, "actor", "unknown"),
    (models.Record, "type", "unknown"),
    (models.Record, "factor", 4),
    (models.Record, "user_status", "unknown"),
    (models.Record, "extracted_by", "unknown"),
    (models.Assignment, "status", "unknown"),
    (models.Finding, "severity", "unknown"),
    (models.FactorStatus, "factor", 4),
    (models.Assessment, "status", "unknown"),
    (models.RiskReport, "verdict", "unknown"),
    (models.RawItem, "provider", "unknown"),
    (models.CandidateRecord, "doc_type", "unknown"),
    (models.CandidateRecord, "factor", 4),
    (models.Metro, "high_cost", "invalid-bool"),
    (models.Record, "date", "invalid-date"),
    (models.Connection, "connected_at", "invalid-datetime"),
    (models.Attachment, "size_bytes", "invalid-int"),
    (models.MonthlyLedgerRow, "home_housing_paid", "invalid-float"),
    (models.Profile, "home_metro", "invalid-metro"),
    (models.Record, "source", None),
    (models.Record, "history", ["invalid-audit-event"]),
])
def test_invalid_values_are_rejected(model, field, value, samples):
    data = samples[model].model_dump()
    data[field] = value
    with pytest.raises(ValidationError) as exc:
        model.model_validate(data)
    assert any(error["loc"][0] == field for error in exc.value.errors())
