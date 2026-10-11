"""Step 10 check: every synthetic sample through pipeline.ingest, live against Akamai.

Run from repo root: .venv\\Scripts\\python scripts\\p1_pipeline_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, team convention
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for p1_samples

from p1_samples import EXPECTED, PROFILE, SAMPLES

from backend.app.agents.extractor import needs_review
from backend.app.agents.pipeline import MAX_REQUESTS_PER_SYNC, CallBudget, ingest


def main() -> int:
    budget, passed = CallBudget(), 0
    for item in SAMPLES:
        relevant, doc_type, suspicious = EXPECTED[item.source_id]
        r = ingest(item, PROFILE, budget)
        actions = [e.action for e in r.events]
        if suspicious:
            ok = r.candidate is None and actions == ["ignored_suspicious"]
        elif relevant:
            ok = r.candidate is not None and r.candidate.doc_type == doc_type and not actions
            if item.source_id == "sample-nearmiss":
                ok = ok and needs_review(r.candidate)
        else:
            ok = r.candidate is None and actions == ["skipped"]
        got = (f"{r.candidate.doc_type} review={needs_review(r.candidate)}" if r.candidate else "-")
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {item.source_id:<16} candidate={got:<28} events={actions}")
    print(f"{passed}/{len(SAMPLES)} passed; model requests used {MAX_REQUESTS_PER_SYNC - budget.left}/{MAX_REQUESTS_PER_SYNC}")
    return 0 if passed == len(SAMPLES) else 1


if __name__ == "__main__":
    sys.exit(main())
