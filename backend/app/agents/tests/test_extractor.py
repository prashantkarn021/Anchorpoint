from datetime import UTC, datetime

from backend.app.agents import extractor
from backend.app.agents.extractor import (
    REVIEW_THRESHOLD,
    enforce,
    extract,
    match_home,
    needs_review,
    pdf_text,
)
from backend.app.models import CandidateRecord, Metro, Profile, RawItem

SOURCE = "We received your rent payment of $1,450.00\non September 1, 2026."
PROFILE = Profile(id="p1", name="Maya Torres", home_address="4120 Linden Ave",
                  home_metro=Metro(name="Kansas City", state="MO"), family_at_home=False)


def _c(**kw) -> CandidateRecord:
    return CandidateRecord(**{"doc_type": "rent_payment", "confidence": 0.9, **kw})


def test_factor_forced_none():
    assert enforce(_c(factor=1), SOURCE).factor is None


def test_invented_quote_dropped_and_capped():
    r = enforce(_c(evidence_quote="paid $9,999 in cash"), SOURCE)
    assert r.evidence_quote is None and needs_review(r)
    r = enforce(_c(evidence_quote="$"), SOURCE)  # in the text, but too short to be evidence
    assert r.evidence_quote is None and needs_review(r)


def test_real_quote_kept_across_whitespace():
    r = enforce(_c(evidence_quote="rent payment of $1,450.00 on September 1"), SOURCE)
    assert r.evidence_quote and r.confidence == 0.9 and not needs_review(r)
    r = enforce(_c(evidence_quote="payment of $1,450.00\\non September 1"), SOURCE)  # literal backslash-n
    assert r.evidence_quote == "payment of $1,450.00 on September 1" and r.confidence == 0.9


def test_home_address_variants_get_profile_spelling():
    home = "4120 Linden Ave, Unit 4B, Kansas City, MO 64111"
    for variant in ["4120 LINDEN AVENUE APT. 4B, Kansas City, MO 64111",
                    "4120 Linden Ave #4B Kansas City MO 64111",
                    "4120 Linden Ave Apt #4B, Kansas City, MO 64111",
                    "4120  linden ave, suite 4b, kansas city, mo 64111"]:
        assert match_home(_c(address=variant), home).address == home
    friend = "77 Brookside Ct, Overland Park, KS 66204"
    assert match_home(_c(address=friend), home).address == friend
    assert match_home(_c(address="4120 Linden Ave, Unit 5C, Kansas City, MO 64111"), home).address != home
    assert match_home(_c(), home).address is None
    assert match_home(_c(address="---"), "").address == "---"  # empty keys never match
    assert match_home(_c(address="100 East St NW"), "100 E St NW").address == "100 East St NW"


def test_confidence_clamped_and_threshold():
    assert enforce(_c(confidence=7.0), SOURCE).confidence == 1.0
    assert enforce(_c(confidence=-1.0), SOURCE).confidence == 0.0
    assert needs_review(_c(confidence=REVIEW_THRESHOLD - 0.01))
    assert not needs_review(_c(confidence=REVIEW_THRESHOLD))


def test_cache_hit_skips_model(monkeypatch):
    calls = []
    monkeypatch.setattr(extractor, "_cache", {})
    monkeypatch.setattr(extractor, "_run_agent", lambda p, budget=None: calls.append(p) or _c())
    item = RawItem(provider="gmail", source_id="a", received_at=datetime(2026, 9, 1, tzinfo=UTC), text=SOURCE)
    same_text_new_id = item.model_copy(update={"source_id": "b"})
    first, cached = extract(item, PROFILE, "rent_payment")
    assert cached is False
    first.confidence = 0.0  # caller mutation must not leak into the cache
    again, cached = extract(same_text_new_id, PROFILE, "rent_payment")
    assert cached is True and again.confidence == 0.9
    assert len(calls) == 1 and "Maya Torres" in calls[0].split("<document-")[0]
    moved = PROFILE.model_copy(update={"home_address": "9 Elm St"})  # profile edit -> fresh extraction
    assert extract(item, moved, "rent_payment")[1] is False and len(calls) == 2


def _tiny_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
         b"/Resources << /Font << /F1 5 0 R >> >> >>"),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


def test_pdf_text_reads_text_layer():
    assert "Lease term 12 months" in pdf_text(_tiny_pdf("Lease term 12 months"))
