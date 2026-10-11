"""Step 6 check: triage agent on the 5 synthetic samples, live against Akamai.

Run from repo root: .venv\\Scripts\\python scripts\\p1_triage_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, team convention
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for p1_samples

from p1_samples import EXPECTED, SAMPLES

from backend.app.agents.triage import triage


def main() -> int:
    passed = 0
    for item in SAMPLES:
        want = EXPECTED[item.source_id]
        try:
            r = triage(item)
            got = (r.relevant, r.doc_type, r.suspicious)
            detail = f"conf={r.confidence:.2f}"
        except Exception as e:  # noqa: BLE001 - report, don't crash: this is a check script
            got, detail = None, f"{type(e).__name__}: {str(e)[:120]}"
        ok = got == want
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {item.source_id:<16} want={want}  got={got}  {detail}")
    print(f"{passed}/{len(SAMPLES)} passed")
    return 0 if passed == len(SAMPLES) else 1


if __name__ == "__main__":
    sys.exit(main())
