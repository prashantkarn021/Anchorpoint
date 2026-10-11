from datetime import UTC, date, datetime

import pytest

from backend.app.connectors.upload import check_receipt
from backend.app.models import CandidateRecord, Record, SourceRef

TODAY = date(2026, 10, 11)
TEXT = "Synthetic Fuel Stop\n2026-10-10\nSubtotal $30.00\nTax $2.50\nTotal $32.50"


def candidate(**updates):
    return CandidateRecord.model_validate({
        "doc_type": "fuel_receipt", "payee": "Synthetic Fuel Stop", "amount": 32.5,
        "dates": [date(2026, 10, 10)], "confidence": 0.95, **updates,
    })


def bank(**updates):
    return Record.model_validate({
        "id": "bank-1", "type": "fuel_receipt", "date": date(2026, 10, 10), "amount": 32.5,
        "payee": "Synthetic Fuel Stop", "extracted_by": "plaid",
        "source": SourceRef(provider="bank", source_id="transaction-1", received_at=datetime(2026, 10, 10, tzinfo=UTC),
                            content_hash="synthetic", snippet="Synthetic bank debit"),
        **updates,
    })


def test_consistent_receipt_passes_basic_checks_but_is_never_authenticated():
    result = check_receipt("photo-1", TEXT, candidate(), [], TODAY)
    assert result.status == "checks_passed"
    assert result.authenticity == "unverified"
    assert result.text == TEXT
    assert result.bank_record_ids == []  # Absence of a bank match does not invalidate cash receipts.


@pytest.mark.parametrize("text,fields,reason", [
    (TEXT.replace("Total $32.50", "Total $50.00"), {}, "does not match"),
    (TEXT.replace("Subtotal $30.00", "Subtotal $20.00"), {}, "do not add up"),
    (TEXT, {"payee": "Invented Store"}, "Merchant"),
    (TEXT, {"amount": None}, "could not be read"),
    (TEXT, {"dates": []}, "single receipt date"),
    (TEXT, {"dates": [date(2026, 10, 12)]}, "future"),
    (TEXT, {"dates": [date(2026, 10, 9)]}, "date could not be verified"),
    (TEXT + "\nSAMPLE", {}, "sample, voided"),
    (TEXT + "\nVoid receipt", {}, "sample, voided"),
    (TEXT.replace("Tax $2.50", "Tax 8.3%"), {}, "breakdown is incomplete"),
])
def test_uncertain_or_inconsistent_receipts_require_review(text, fields, reason):
    result = check_receipt("photo-1", text, candidate(**fields), [], TODAY)
    assert result.status == "needs_review"
    assert result.authenticity == "unverified"
    assert any(reason in message for message in result.messages)


def test_bank_match_corroborates_but_does_not_prove_authenticity():
    result = check_receipt("photo-1", TEXT, candidate(), [bank()], TODAY)
    assert result.bank_record_ids == ["bank-1"]
    assert result.authenticity == "unverified"
    assert any("does not prove authenticity" in message for message in result.messages)


@pytest.mark.parametrize("fields", [{"user_status": "rejected"}, {"amount": 300},
                                    {"payee": "Different Store"}, {"date": date(2026, 9, 1)}])
def test_bank_match_requires_unrejected_evidence_with_matching_merchant_amount_and_date(fields):
    result = check_receipt("photo-1", TEXT, candidate(), [bank(**fields)], TODAY)
    assert result.bank_record_ids == []


def test_merchant_partial_word_is_not_accepted_as_printed_evidence():
    result = check_receipt("photo-1", TEXT.replace("Stop", "Stopper"), candidate(), [], TODAY)
    assert result.status == "needs_review"
    assert any("Merchant" in message for message in result.messages)


def test_discounts_and_tips_are_accounted_for_with_decimal_precision():
    text = "Synthetic Fuel Stop\n2026-10-10\nSubtotal $30.00\nTax $2.50\nDiscount $5.00\nTip $5.00\nTotal $32.50"
    assert check_receipt("photo-1", text, candidate(), [], TODAY).status == "checks_passed"
