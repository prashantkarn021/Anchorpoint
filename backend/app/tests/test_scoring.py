"""Pins the demo story: Maya's seeded data, through the real mappers and rules, gives the planned result."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from backend.app import scoring
from backend.app.ledger import Ledger
from backend.app.main import app
from backend.app.models import Assignment, Profile, RawItem, Record
from backend.app.routers.records import get_ledger
from backend.app.routers.stubs import load_fixture
from backend.app.rules.engine import load_rates
from backend.app.seed.bank import bank_transactions
from backend.app.seed.persona import Persona
from backend.app.sync.mapping import record_from_bank

TODAY = date(2026, 10, 11)
PROFILE = load_fixture("profile.json", TypeAdapter(Profile))
ASSIGNMENTS = load_fixture("assignments.json", TypeAdapter(list[Assignment]))
RATES = load_rates()


def bank_records() -> list[Record]:
    """Maya's planted bank history, mapped exactly as the sync maps it."""
    records = []
    for index, row in enumerate(bank_transactions(Persona.load("maya", TODAY))):
        day = date.fromisoformat(row["date_posted"])
        item = RawItem(
            provider="bank", source_id=f"t{index}",
            received_at=datetime(day.year, day.month, day.day, tzinfo=UTC),
            text=f"{row['date_posted']}  {row['description']}  {row['amount']:.2f} USD",
            meta={"merchant": row["description"], "amount": row["amount"]},
        )
        if (record := record_from_bank(item, PROFILE.home_metro.name)) is not None:
            records.append(record)
    return records


def anchor(record_type: str) -> Record:
    return Record.model_validate({
        "id": f"gmail-{record_type}", "type": record_type, "factor": 3, "date": "2026-05-17",
        "address": PROFILE.home_address, "extracted_by": "agent",
        "source": {"provider": "gmail", "source_id": record_type, "received_at": "2026-05-17T15:00:00Z",
                   "snippet": record_type, "content_hash": record_type},
    })


def maya() -> list[Record]:
    return bank_records() + [anchor(t) for t in scoring.ANCHORS]


def rules(assessment) -> dict[str, str]:
    return {finding.rule_id: finding.severity for finding in assessment.findings}


def test_maya_needs_attention_with_the_three_planned_warnings():
    assessment = scoring.assess(maya(), ASSIGNMENTS, PROFILE, TODAY, RATES)

    assert rules(assessment) == {"R1": "warn", "R3": "warn", "R5": "warn"}
    assert assessment.status == "needs_attention"
    assert assessment.factors_met == 2
    assert [(f.factor, f.met) for f in assessment.factors] == [(1, False), (2, True), (3, True)]
    assert 50 <= assessment.score < 75


def test_the_missing_month_is_the_planted_one_and_findings_cite_real_records():
    records = maya()
    assessment = scoring.assess(records, ASSIGNMENTS, PROFILE, TODAY, RATES)
    housing = next(f for f in assessment.findings if f.rule_id == "R1")
    ids = {record.id for record in records}

    assert "2026-06" in housing.detail
    assert "2026-05" not in housing.detail
    assert set(housing.record_ids) <= ids
    assert all(set(factor.record_ids) <= ids for factor in assessment.factors)


def test_finding_the_missing_rent_clears_the_housing_warning_and_raises_the_score():
    records = maya()
    before = scoring.assess(records, ASSIGNMENTS, PROFILE, TODAY, RATES)
    june = next(r for r in records if r.type == "rent_payment").model_copy(
        update={"id": "bank-june", "date": date(2026, 6, 2)}
    )

    after = scoring.assess([*records, june], ASSIGNMENTS, PROFILE, TODAY, RATES)

    assert "R1" not in rules(after)
    assert after.score > before.score


def test_rejected_records_do_not_count():
    records = [
        r.model_copy(update={"user_status": "rejected"}) if r.type == "rent_payment" else r
        for r in maya()
    ]

    assessment = scoring.assess(records, ASSIGNMENTS, PROFILE, TODAY, RATES)

    assert rules(assessment)["R1"] == "high"
    assert assessment.factors[1].met is False


def test_no_evidence_at_all_is_at_risk():
    assessment = scoring.assess([], ASSIGNMENTS, PROFILE, TODAY, RATES)

    assert assessment.status == "at_risk"
    assert assessment.factors[1].score == 0


def test_the_offer_turns_the_one_year_clock_high_and_trips_the_stipend_ceiling():
    offer = next(a for a in ASSIGNMENTS if a.status == "offered")

    current = scoring.run_rules(scoring.counted(maya()), ASSIGNMENTS, PROFILE, TODAY, RATES)
    with_offer = scoring.run_rules(scoring.counted(maya()), ASSIGNMENTS, PROFILE, TODAY, RATES, offer)

    assert scoring.verdict(current) == "review_with_cpa"
    assert {f.rule_id: f.severity for f in with_offer}["R5"] == "high"
    assert "R7" in {f.rule_id for f in with_offer}
    assert "R7" not in {f.rule_id for f in current}
    assert scoring.verdict(with_offer) == "high_risk"
    assert scoring.verdict([]) == "go"


def test_monthly_rows_show_the_hole_and_do_not_double_count_email_and_bank():
    records = maya()
    emailed_rent = next(r for r in records if r.type == "rent_payment").model_copy(update={
        "id": "gmail-rent", "date": date(2026, 3, 3),
        "source": anchor("lease").source.model_copy(update={"source_id": "rent-email"}),
    })

    rows = {row.month: row for row in scoring.monthly_rows([*records, emailed_rent], ASSIGNMENTS, TODAY)}

    assert list(rows) == [f"{2025 + (9 + i) // 12}-{(9 + i) % 12 + 1:02d}" for i in range(12)]
    assert rows["2026-06"].missing == ["rent"]
    assert rows["2026-06"].home_housing_paid == 0
    assert rows["2026-03"].home_housing_paid == 1150.0
    assert rows["2026-03"].missing == []
    assert all(row.home_utilities_paid > 0 for row in rows.values())
    assert rows["2026-07"].stipends_received == pytest.approx(31 / 7 * 1505, abs=0.01)


def test_the_endpoints_compute_from_the_ledger(tmp_path):
    ledger = Ledger(str(tmp_path / "assessment.db"))
    for record in maya():
        ledger.upsert_record(record)
    app.dependency_overrides[get_ledger] = lambda: ledger
    try:
        client = TestClient(app)
        assessment = client.get("/api/assessment").json()
        monthly = client.get("/api/ledger/monthly").json()
    finally:
        app.dependency_overrides.clear()

    assert assessment["factors_met"] in (2, 3)
    assert {f["rule_id"] for f in assessment["findings"]} >= {"R3"}
    assert len(monthly) == 12
