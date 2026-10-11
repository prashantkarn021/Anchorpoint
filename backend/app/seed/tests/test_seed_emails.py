import io
from collections import Counter
from datetime import date, datetime
from email import message_from_bytes

from pypdf import PdfReader

from backend.app.seed.emails import CENTRAL, generate, inject_emails
from backend.app.seed.gmail_writer import to_mime
from backend.app.seed.persona import Persona

TODAY = date(2026, 10, 11)
WINDOW = [f"{2025 + (9 + i) // 12}-{(9 + i) % 12 + 1:02d}" for i in range(12)]  # 2025-10 .. 2026-09


def maya() -> Persona:
    return Persona.load("maya", TODAY)


def months(emails, record, kind="evidence") -> list[str]:
    return sorted(
        f"{email.sent_at:%Y-%m}" for email in emails if email.record == record and email.kind == kind
    )


def by_template(emails, template):
    return [email for email in emails if f"-{template}-" in email.key]


def test_relative_dates_resolve_from_seed_day():
    persona = maya()

    assert persona.resolve({"mo": -4, "day": 3}) == date(2026, 6, 3)
    assert persona.resolve({"mo": -8, "day": 31}) == date(2026, 2, 28)
    assert persona.resolve({"wk": -30, "day": 1}) == date(2026, 3, 10)
    assert persona.start("denver-1") == date(2025, 12, 8)


def test_rent_receipts_cover_eleven_months_and_skip_the_planted_one():
    rent = months(by_template(generate(maya()), "rent_received"), "rent_payment")

    assert rent == [month for month in WINDOW if month != "2026-06"]


def test_utility_bills_cover_every_month_of_the_rules_window():
    emails = generate(maya())

    assert months(by_template(emails, "electric_bill"), "utility_bill") == WINDOW
    assert months(by_template(emails, "internet_bill"), "utility_bill") == WINDOW


def test_home_documents_print_the_profile_address_verbatim():
    persona = maya()
    home = persona.profile["home_address"]
    with_address = {
        entry["template"] for entry in persona.spec["emails"] if entry.get("address") == "home"
    }

    for email in generate(persona):
        if email.kind == "evidence" and any(f"-{t}-" in email.key for t in with_address):
            assert home in email.body, email.key


def test_internet_bills_carry_no_address():
    for email in by_template(generate(maya()), "internet_bill"):
        assert "Kansas City" not in email.body


def test_gap_trips_fall_inside_their_breaks_and_the_first_gap_has_none():
    persona = maya()
    flights = by_template(generate(persona), "flight_itinerary")
    sent = sorted(email.sent_at.date() for email in flights)

    assert len(flights) == 3
    assert persona.end("denver-1") <= sent[0] <= persona.start("denver-2")
    assert persona.end("denver-2") <= sent[1] <= persona.start("denver-3")
    for depart, back in persona.trips()[:2]:
        assert depart <= back
        assert any(depart == day for day in sent)
    gap_start, gap_end = persona.end("tucson"), persona.start("denver-1")
    assert not [day for day in sent if gap_start <= day <= gap_end]


def test_near_miss_rent_receipt_stays_out_of_the_missing_month():
    near = [email for email in generate(maya()) if email.kind == "near_miss"]

    assert len(near) == 2
    assert all(email.record is None for email in near)
    assert all(f"{email.sent_at:%Y-%m}" != "2026-06" for email in near)
    assert all("Maya Torres" not in email.body.split("\n", 2)[2] for email in near)


def test_inbox_has_noise_one_hostile_email_and_nothing_from_the_future():
    emails = generate(maya())
    kinds = Counter(email.kind for email in emails)

    assert kinds["noise"] == 50
    assert kinds["hostile"] == 1
    assert kinds["evidence"] == 65
    assert max(email.sent_at.date() for email in emails) <= TODAY
    assert emails == sorted(emails, key=lambda email: email.sent_at)


def test_generation_is_deterministic():
    first, second = generate(maya()), generate(maya())

    assert [to_mime(e, "Maya Torres", "maya@example.com") for e in first] == [
        to_mime(e, "Maya Torres", "maya@example.com") for e in second
    ]


def test_pdf_attachments_are_readable_and_carry_the_address():
    persona = maya()
    bill = by_template(generate(persona), "electric_bill")[0]
    filename, mime_type, data = bill.attachments[0]

    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)

    assert filename.endswith(".pdf") and mime_type == "application/pdf"
    assert persona.profile["home_address"] in text
    assert "Amount due" in text


def test_mime_message_is_backdated_and_addressed_to_the_demo_account():
    bill = by_template(generate(maya()), "electric_bill")[0]

    message = message_from_bytes(to_mime(bill, "Maya Torres", "maya@example.com"))

    assert message["To"] == "Maya Torres <maya@example.com>"
    assert message["From"] == "Evergreen Power & Light <billing@evergreenpl.example>"
    assert message["Date"].startswith("Tue, 14 Oct 2025")
    assert [part.get_filename() for part in message.walk() if part.get_filename()]


def test_inject_email_is_a_fresh_home_utility_bill():
    persona = maya()
    now = datetime(2026, 10, 11, 9, 30, tzinfo=CENTRAL)

    (email,) = inject_emails(persona, now)

    assert email.sent_at == now
    assert persona.profile["home_address"] in email.body
    assert "$87.42" in email.body
