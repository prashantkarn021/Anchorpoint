"""R2: utility continuity. Human-written acceptance tests; do not edit to make code pass.

Definition: look at the 12 full calendar months BEFORE the month of `today`.
Each month needs at least one utility_bill or utility_payment record that is not rejected
and whose address matches the home address (case/spacing ignored) or has no address
(bank autopay records carry none). Any missing month = one warn finding listing the months.
"""

from datetime import date, datetime

from backend.app.models import Record, SourceRef
from backend.app.rules.engine import check_utility_continuity

TODAY = date(2026, 10, 10)  # window is Oct 2025 .. Sep 2026
HOME = "1200 Example St, Kansas City, MO"


def rec(rid, rtype, d, address=HOME, status="pending"):
    return Record(
        id=rid,
        type=rtype,
        date=d,
        amount=95.0,
        payee="Evergreen Power & Light",
        address=address,
        user_status=status,
        source=SourceRef(
            provider="gmail",
            source_id=f"msg-{rid}",
            received_at=datetime(d.year, d.month, d.day),
            snippet="Your bill is ready",
            content_hash="h",
        ),
        extracted_by="agent",
    )


def window_months():
    return [date(2025, m, 1) for m in (10, 11, 12)] + [date(2026, m, 1) for m in range(1, 10)]


def full_window(skip=()):
    return [
        rec(f"u{d.year}-{d.month}", "utility_bill", d)
        for d in window_months()
        if d.strftime("%Y-%m") not in skip
    ]


def test_all_twelve_months_present_gives_no_finding():
    assert check_utility_continuity(full_window(), TODAY, HOME) == []


def test_one_missing_month_is_warn_and_names_it():
    findings = check_utility_continuity(full_window(skip={"2026-06"}), TODAY, HOME)
    assert len(findings) == 1
    assert findings[0].rule_id == "R2"
    assert findings[0].severity == "warn"
    assert "2026-06" in findings[0].detail


def test_several_missing_months_are_still_one_warn_finding():
    findings = check_utility_continuity(full_window(skip={"2025-11", "2026-07"}), TODAY, HOME)
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "2025-11" in findings[0].detail and "2026-07" in findings[0].detail


def test_utility_payment_from_bank_counts_like_a_bill():
    records = [
        rec(f"p{d.year}-{d.month}", "utility_payment", d, address=None) for d in window_months()
    ]
    assert check_utility_continuity(records, TODAY, HOME) == []


def test_bill_for_a_different_address_does_not_count():
    records = full_window()
    records[5] = rec("other", "utility_bill", records[5].date, address="55 Elsewhere Ave, Wichita, KS")
    findings = check_utility_continuity(records, TODAY, HOME)
    assert len(findings) == 1 and records[5].date.strftime("%Y-%m") in findings[0].detail


def test_address_match_ignores_case_and_extra_spacing():
    messy = "  1200  EXAMPLE st,  kansas city, mo "
    records = [rec(f"c{d.year}-{d.month}", "utility_bill", d, address=messy) for d in window_months()]
    assert check_utility_continuity(records, TODAY, HOME) == []


def test_rejected_record_does_not_count():
    records = full_window()
    records[0] = rec("rej", "utility_bill", date(2025, 10, 1), status="rejected")
    findings = check_utility_continuity(records, TODAY, HOME)
    assert len(findings) == 1 and "2025-10" in findings[0].detail


def test_current_month_is_ignored():
    # Nothing in October 2026 yet; that must not count as missing.
    assert check_utility_continuity(full_window(), TODAY, HOME) == []


def test_no_records_at_all_is_warn_listing_all_twelve_months():
    findings = check_utility_continuity([], TODAY, HOME)
    assert len(findings) == 1 and findings[0].severity == "warn"
    for d in window_months():
        assert d.strftime("%Y-%m") in findings[0].detail
