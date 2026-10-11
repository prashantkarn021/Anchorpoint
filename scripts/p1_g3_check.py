"""Gate G3: Plaid custom sandbox user returns planted transactions via /transactions/sync.

Plants 12 months of rent with one month missing (rule R1's hole) plus a few other txns,
creates a fresh sandbox Item, syncs, and checks the rent gap comes back exactly.

Run from repo root: .venv\\Scripts\\python scripts\\p1_g3_check.py
"""

import json
import os
import sys
import time
from datetime import date, timedelta

import plaid
from dotenv import load_dotenv
from plaid.api import plaid_api
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import (
    SandboxPublicTokenCreateRequest,
)
from plaid.model.sandbox_public_token_create_request_options import (
    SandboxPublicTokenCreateRequestOptions,
)
from plaid.model.sandbox_public_token_create_request_options_transactions import (
    SandboxPublicTokenCreateRequestOptionsTransactions,
)
from plaid.model.transactions_sync_request import TransactionsSyncRequest

RENT_PAYEE = "Westport Property Mgmt"
MISSING_MONTHS_BACK = 4  # the planted hole
INSTITUTION = "ins_109508"  # First Platypus Bank (non-OAuth sandbox bank)


def month_start(today: date, back: int) -> date:
    y, m = divmod(today.year * 12 + today.month - 1 - back, 12)
    return date(y, m + 1, 1)


def planted(today: date) -> list[dict]:
    """~20 synthetic txns, dated relative to today. Plaid amounts: positive = money out."""
    rent = [
        (month_start(today, b), 1450.00, f"{RENT_PAYEE} ACH RENT")
        for b in range(12)
        if b != MISSING_MONTHS_BACK
    ]
    d = lambda n: today - timedelta(days=n)
    other = [
        (d(3), 112.40, "Evergreen Power & Light AUTOPAY"),
        (d(33), 98.75, "Evergreen Power & Light AUTOPAY"),
        (d(5), 64.99, "PlainsNet Internet AUTOPAY"),
        (d(7), -1050.00, "Northbridge Staffing STIPEND"),
        (d(14), -1050.00, "Northbridge Staffing STIPEND"),
        (d(10), 2100.00, "StayLocal Furnished Rentals"),
        (d(20), 238.60, "Skyline Air DEN-MCI"),
        (d(2), 41.18, "Fuel Stop 22"),
        (d(1), 23.45, "Prairie Grocer"),
    ]
    return [
        {"date_transacted": t.isoformat(), "date_posted": t.isoformat(), "amount": a,
         "description": desc, "currency": "USD"}
        for t, a, desc in rent + other
    ]


def main() -> int:
    load_dotenv()
    client = plaid_api.PlaidApi(plaid.ApiClient(plaid.Configuration(
        host=plaid.Environment.Sandbox,
        api_key={"clientId": os.environ["PLAID_CLIENT_ID"], "secret": os.environ["PLAID_SECRET"]},
    )))

    today = date.today()
    txns = planted(today)
    user = {"override_accounts": [{
        "type": "depository", "subtype": "checking", "starting_balance": 8000,
        "meta": {"name": "Synthetic Checking"}, "transactions": txns,
    }]}

    public_token = client.sandbox_public_token_create(SandboxPublicTokenCreateRequest(
        institution_id=INSTITUTION,
        initial_products=[Products("transactions")],
        options=SandboxPublicTokenCreateRequestOptions(
            override_username="user_custom",
            override_password=json.dumps(user),
            transactions=SandboxPublicTokenCreateRequestOptionsTransactions(days_requested=400),
        ),
    )).public_token
    access_token = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    ).access_token  # never printed

    try:
        added, cursor, deadline = [], None, time.time() + 60
        while True:
            req = TransactionsSyncRequest(access_token=access_token, **({"cursor": cursor} if cursor else {}))
            r = client.transactions_sync(req)
            added += r.added
            cursor = r.next_cursor
            if r.has_more:
                continue
            status = str(r.transactions_update_status)
            if status == "HISTORICAL_UPDATE_COMPLETE":
                break
            if time.time() > deadline:
                print(f"WARN  timed out waiting for HISTORICAL_UPDATE_COMPLETE (status={status})")
                break
            time.sleep(2)
    # ponytail: no TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION restart; the step 8 connector needs one
    finally:
        try:
            client.item_remove(ItemRemoveRequest(access_token=access_token))
        except plaid.ApiException as e:  # don't mask a sync error with a cleanup error
            print(f"WARN  item_remove failed: {e.status}")

    for t in sorted(added, key=lambda t: t.date):
        print(f"  {t.date}  {t.amount:>9.2f}  {t.name}")

    rent_months = {t.date.strftime("%Y-%m") for t in added if "westport" in t.name.lower()}
    expected = {month_start(today, b).strftime("%Y-%m") for b in range(12)}
    missing = sorted(expected - rent_months)
    want = [month_start(today, MISSING_MONTHS_BACK).strftime("%Y-%m")]

    ok_count = len(added) == len(txns)
    ok_gap = missing == want
    print(f"{'PASS' if ok_count else 'FAIL'}  transactions returned  {len(added)}/{len(txns)}")
    print(f"{'PASS' if ok_gap else 'FAIL'}  rent gap  missing={missing} expected={want}")
    return 0 if ok_count and ok_gap else 1


if __name__ == "__main__":
    sys.exit(main())
