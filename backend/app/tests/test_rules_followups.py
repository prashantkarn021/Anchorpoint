"""PR #6 review follow-ups: R2 address normalization, R1/R2 period_start month key."""

from datetime import date, datetime

from backend.app.common.address import address_key
from backend.app.models import Record, SourceRef
from backend.app.rules.engine import check_housing_continuity, check_utility_continuity

TODAY = date(2026, 10, 10)  # window is Oct 2025 .. Sep 2026
HOME = "4120 Linden Ave, Unit 4B, Kansas City, MO 64111"
WINDOW = [date(2025, m, 1) for m in (10, 11, 12)] + [date(2026, m, 1) for m in range(1, 10)]


def rec(rid, rtype, d, address=None, period_start=None):
    return Record(
        id=rid, type=rtype, date=d, period_start=period_start, address=address,
        source=SourceRef(provider="gmail", source_id=rid, received_at=datetime(2026, 1, 1),
                         snippet="s", content_hash="h"),
        extracted_by="agent",
    )


def test_address_key_folds_street_and_unit_spellings():
    assert address_key("4120 Linden Avenue, Unit 4-B, Kansas City, MO 64111") == address_key(HOME)
    assert address_key("4120 linden ave apt 4b kansas city mo 64111") == address_key(HOME)
    assert address_key("4120 Linden Ave, Unit 5C, Kansas City, MO 64111") != address_key(HOME)


def test_r2_counts_bill_with_differently_spelled_home_address():
    variant = "4120 Linden Avenue Apt 4-B, Kansas City, MO 64111"
    records = [rec(f"u{d:%Y%m}", "utility_bill", d, address=variant) for d in WINDOW]
    assert check_utility_continuity(records, TODAY, HOME) == []


def test_r2_empty_home_address_matches_nothing_with_an_address():
    records = [rec(f"u{d:%Y%m}", "utility_bill", d, address="---") for d in WINDOW]
    assert len(check_utility_continuity(records, TODAY, "")) == 1


def test_r1_uses_period_start_over_payment_date():
    # September's rent paid on Aug 28 covers September, not August.
    records = [rec(f"r{d:%Y%m}", "rent_payment", d) for d in WINDOW if d.month != 9]
    records.append(rec("early", "rent_payment", date(2026, 8, 28), period_start=date(2026, 9, 1)))
    assert check_housing_continuity(records, TODAY) == []


def test_r2_uses_period_start_over_bill_date():
    # A bill issued Oct 3 for the September period fills September.
    records = [rec(f"u{d:%Y%m}", "utility_bill", d) for d in WINDOW if d.month != 9]
    records.append(rec("late", "utility_bill", date(2026, 10, 3), period_start=date(2026, 9, 1)))
    assert check_utility_continuity(records, TODAY, HOME) == []
