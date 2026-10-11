from datetime import date

from backend.app.seed.bank import DEFAULT_LIMIT, bank_transactions
from backend.app.seed.persona import Persona

TODAY = date(2026, 10, 11)
WINDOW = [f"{2025 + (9 + i) // 12}-{(9 + i) % 12 + 1:02d}" for i in range(12)]  # 2025-10 .. 2026-09


def maya() -> Persona:
    return Persona.load("maya", TODAY)


def named(transactions, text):
    return [t for t in transactions if text in t["description"]]


def months(transactions):
    return sorted({t["date_posted"][:7] for t in transactions})


def test_rows_use_plaids_custom_user_format():
    transactions = bank_transactions(maya())

    assert set(transactions[0]) == {"date_transacted", "date_posted", "amount", "description", "currency"}
    assert all(t["currency"] == "USD" and t["date_posted"] == t["date_transacted"] for t in transactions)
    assert [t["date_posted"] for t in transactions] == sorted(t["date_posted"] for t in transactions)


def test_rent_is_paid_eleven_months_and_missing_for_the_planted_one():
    rent = named(bank_transactions(maya()), "WESTPORT PROPERTY MGMT ACH")

    assert months(rent) == [month for month in WINDOW if month != "2026-06"]
    assert {t["amount"] for t in rent} == {1150.0}
    assert all(t["date_posted"].endswith("-02") for t in rent)


def test_utilities_autopay_in_every_month_of_the_rules_window():
    transactions = bank_transactions(maya())

    for name in ("EVERGREEN POWER & LIGHT AUTOPAY", "PLAINSNET INTERNET"):
        assert set(WINDOW) <= set(months(named(transactions, name))), name


def test_denver_lodging_is_charged_in_the_missing_rent_month():
    lodging = named(bank_transactions(maya()), "STAYLOCAL FURNISHED RENTALS")

    assert "2026-06" in months(lodging)
    assert months(lodging)[0] == "2025-12"


def test_trip_spending_falls_inside_the_trips_and_nowhere_else():
    persona = maya()
    transactions = bank_transactions(persona)
    trips = persona.trips()
    home_side = named(transactions, "SKYLINE AIR") + named(transactions, "KANSAS CITY")

    assert len(named(transactions, "SKYLINE AIR")) == 3
    for transaction in home_side:
        day = date.fromisoformat(transaction["date_posted"])
        assert any(depart <= day <= back for depart, back in trips), transaction


def test_the_gap_without_a_trip_shows_nothing_at_home():
    persona = maya()
    gap_start, gap_end = persona.end("tucson"), persona.start("denver-1")

    in_gap = [
        t for t in bank_transactions(persona)
        if gap_start <= date.fromisoformat(t["date_posted"]) <= gap_end
    ]

    assert not named(in_gap, "KANSAS CITY")
    assert not named(in_gap, "SKYLINE AIR")


def test_deposits_are_negative_and_match_the_assignment_pay():
    transactions = bank_transactions(maya())
    stipends = named(transactions, "NORTHBRIDGE STAFFING STIPEND")
    payroll = named(transactions, "NORTHBRIDGE STAFFING PAYROLL")

    assert {t["amount"] for t in stipends} == {-1505.0}
    assert len(stipends) > 40
    assert all(t["amount"] < 0 for t in payroll)
    assert 20 <= len(payroll) <= 27


def test_fits_the_limit_stays_in_the_past_and_is_deterministic():
    transactions = bank_transactions(maya())

    assert len(transactions) == DEFAULT_LIMIT
    assert max(t["date_posted"] for t in transactions) <= TODAY.isoformat()
    assert min(t["date_posted"] for t in transactions) >= "2025-10-01"
    assert transactions == bank_transactions(maya())


def test_a_small_limit_keeps_the_whole_story():
    transactions = bank_transactions(maya(), limit=10)

    assert len(named(transactions, "WESTPORT PROPERTY MGMT ACH")) == 11
    assert not named(transactions, "PEAKSIDE GROCER")
