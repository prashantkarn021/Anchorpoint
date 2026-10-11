"""R1: housing continuity. Human-written acceptance tests; do not edit to make code pass.

Definition: look at the 12 full calendar months BEFORE the month of `today`.
Each month needs at least one rent_payment or mortgage record that is not rejected.
1 missing month = warn, 2 or more = high, 0 = no finding.
"""

from datetime import date, datetime

from backend.app.models import Record, SourceRef
from backend.app.rules.engine import check_housing_continuity

TODAY = date(2026, 10, 10)  # window is Oct 2025 .. Sep 2026


def rec(rid, rtype, d, status="pending"):
    return Record(
        id=rid,
        type=rtype,
        date=d,
        amount=1450.0,
        payee="Westport Property Mgmt",
        user_status=status,
        source=SourceRef(
            provider="bank",
            source_id=f"txn-{rid}",
            received_at=datetime(d.year, d.month, d.day),
            snippet="ACH rent",
            content_hash="h",
        ),
        extracted_by="plaid",
    )


def window_months():
    return [date(2025, m, 1) for m in (10, 11, 12)] + [date(2026, m, 1) for m in range(1, 10)]


def full_year(skip=()):
    return [
        rec(f"r{d.month}-{d.year}", "rent_payment", d)
        for d in window_months()
        if d.strftime("%Y-%m") not in skip
    ]


def test_all_twelve_months_present_gives_no_finding():
    assert check_housing_continuity(full_year(), TODAY) == []


def test_one_missing_month_is_warn_and_names_the_month():
    findings = check_housing_continuity(full_year(skip={"2026-03"}), TODAY)
    assert len(findings) == 1
    assert findings[0].rule_id == "R1"
    assert findings[0].severity == "warn"
    assert "2026-03" in findings[0].detail


def test_two_missing_months_is_high():
    findings = check_housing_continuity(full_year(skip={"2026-03", "2026-05"}), TODAY)
    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert "2026-03" in findings[0].detail and "2026-05" in findings[0].detail


def test_mortgage_payment_counts_like_rent():
    records = [rec(f"m{d.month}-{d.year}", "mortgage", d) for d in window_months()]
    assert check_housing_continuity(records, TODAY) == []


def test_rejected_record_does_not_count():
    records = full_year()
    records[5] = rec("rejected", "rent_payment", records[5].date, status="rejected")
    findings = check_housing_continuity(records, TODAY)
    assert len(findings) == 1 and findings[0].severity == "warn"


def test_two_payments_in_one_month_count_once():
    records = full_year() + [rec("dup", "rent_payment", date(2026, 3, 15))]
    assert check_housing_continuity(records, TODAY) == []


def test_current_month_is_ignored():
    # Nothing in October 2026 yet; that must not count as missing.
    assert check_housing_continuity(full_year(), TODAY) == []


def test_no_records_at_all_is_high():
    findings = check_housing_continuity([], TODAY)
    assert len(findings) == 1 and findings[0].severity == "high"
