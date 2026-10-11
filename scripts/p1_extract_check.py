"""Step 7 check: triage -> extractor on the relevant samples, live against Akamai; second pass must be cached.

Run from repo root: .venv\\Scripts\\python scripts\\p1_extract_check.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, team convention
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for p1_samples

from p1_samples import EXPECTED, PROFILE, SAMPLES

from backend.app.agents.extractor import extract, needs_review
from backend.app.agents.triage import triage

# source_id -> fields that must match exactly (needs_review is computed, not a CandidateRecord field)
CHECKS = {
    "sample-rent": {"amount": 1450.0, "period_start": date(2026, 9, 1), "period_end": date(2026, 9, 30),
                    "needs_review": False},
    "sample-electric": {"amount": 98.75, "needs_review": False, "address": PROFILE.home_address},  # variant folded
    "sample-nearmiss": {"needs_review": True},
    "sample-lease": {"period_start": date(2026, 1, 1), "period_end": date(2026, 12, 31), "needs_review": False},
    "sample-paystub": {"needs_review": False},
}


def main() -> int:
    items = [s for s in SAMPLES if s.source_id in CHECKS]
    passed, types = 0, {}
    for item in items:
        try:
            t = triage(item)
            if t.doc_type != EXPECTED[item.source_id][1]:
                raise ValueError(f"triage gave {t.doc_type}")
            types[item.source_id] = t.doc_type
            c, cached = extract(item, PROFILE, t.doc_type)
            got = {**c.model_dump(), "needs_review": needs_review(c)}
            bad = {k: got[k] for k, v in CHECKS[item.source_id].items() if got[k] != v}
            ok = not bad and not cached
            detail = (f"type={c.doc_type} amount={c.amount} period={c.period_start}..{c.period_end} "
                      f"conf={c.confidence:.2f} review={got['needs_review']} quote={c.evidence_quote!r}"
                      + (f"  MISMATCH {bad}" if bad else ""))
        except Exception as e:  # noqa: BLE001 - report, don't crash: this is a check script
            ok, detail = False, f"{type(e).__name__}: {str(e)[:120]}"
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {item.source_id:<16} {detail}")

    hits = sum(extract(i, PROFILE, types[i.source_id])[1] for i in items if i.source_id in types)
    print(f"{passed}/{len(items)} passed; second pass cache hits {hits}/{len(items)}")
    return 0 if passed == len(items) and hits == len(items) else 1


if __name__ == "__main__":
    sys.exit(main())
