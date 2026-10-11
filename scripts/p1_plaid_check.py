"""Step 8 check: PlaidConnector against the live sandbox with Maya's planted bank data.

Run from repo root: .venv\\Scripts\\python scripts\\p1_plaid_check.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, team convention
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for p1_samples

from p1_samples import RENT_MERCHANT, RENT_MISSING_MO, bank_transactions, mo

from backend.app.connectors.plaid import PlaidConnector


def main() -> int:
    today = date.today()
    planted = bank_transactions(today)
    conn = PlaidConnector(planted)
    try:
        connection = conn.finish_auth({"public_token": conn.start_auth()})
        print(f"connected: {connection.id} status={connection.status}")
        items, cursor = conn.fetch_since(None)
        again, _ = conn.fetch_since(cursor)
    finally:
        conn.revoke()

    for i in sorted(items, key=lambda i: i.received_at):
        print(f"  {i.text}   merchant={i.meta['merchant']!r}")

    rent = {i.received_at.strftime("%Y-%m") for i in items if i.meta["merchant"] == RENT_MERCHANT}
    expected = {mo(today, n, 1).strftime("%Y-%m") for n in range(-12, 0)}
    missing, want = sorted(expected - rent), [mo(today, RENT_MISSING_MO, 1).strftime("%Y-%m")]
    checks = [
        (f"items returned {len(items)}/{len(planted)}", len(items) == len(planted)),
        (f"rent gap missing={missing} expected={want}", missing == want),
        (f"second sync returns nothing new ({len(again)})", not again),
    ]
    for label, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
