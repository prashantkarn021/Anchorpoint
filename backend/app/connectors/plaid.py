"""Plaid bank connector (sandbox): transactions -> RawItem + meta. No LLM: P2's sync maps them to Records.

Sandbox shortcut, no Link UI: start_auth() creates a custom-user Item from the planted
transactions and returns its public_token; finish_auth() exchanges it. Demo reset =
revoke() + start_auth() + finish_auth() (Plaid custom dates are absolute, so re-plant fresh ones).
"""

import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime

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

from backend.app.models import Connection, RawItem

log = logging.getLogger(__name__)

INSTITUTION = "ins_109508"  # First Platypus Bank (non-OAuth sandbox bank)
HISTORY_WAIT_S = 60
SETTLE_S = 3
MUTATION = "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"


def _client() -> plaid_api.PlaidApi:
    load_dotenv()
    if os.environ.get("PLAID_ENV", "sandbox") != "sandbox":
        raise RuntimeError("PlaidConnector is sandbox-only")
    return plaid_api.PlaidApi(plaid.ApiClient(plaid.Configuration(
        host=plaid.Environment.Sandbox,
        api_key={"clientId": os.environ["PLAID_CLIENT_ID"], "secret": os.environ["PLAID_SECRET"]},
    )))


def to_raw_item(t) -> RawItem:
    """One Plaid transaction -> RawItem. Plaid sign kept: positive amount = money out.

    meta["merchant"] is the raw bank descriptor (`name`), not Plaid's `merchant_name`: the
    enrichment guesses (live sandbox: "PLAINSNET INTERNET" -> "Plains Internet"), so it's kept
    separately as a hint only.
    """
    amount = float(t.amount)
    return RawItem(
        provider="bank",
        source_id=t.transaction_id,
        received_at=datetime(t.date.year, t.date.month, t.date.day, tzinfo=UTC),
        text=f"{t.date.isoformat()}  {t.name}  {abs(amount):.2f} {t.iso_currency_code or 'USD'} "
             f"({'debit' if amount > 0 else 'credit'})",
        meta={"merchant": t.name, "merchant_name": t.merchant_name, "amount": amount, "date": t.date.isoformat(),
              "account_id": t.account_id, "iso_currency_code": t.iso_currency_code},
    )


class PlaidConnector:
    provider = "bank"

    def __init__(self, transactions: list[dict], client=None):
        self.transactions = transactions  # Plaid custom-user override format
        self.client = client or _client()
        self._access_token: str | None = None  # never logged or returned

    def start_auth(self) -> str:
        user = {"override_accounts": [{
            "type": "depository", "subtype": "checking", "starting_balance": 8000,
            "meta": {"name": "Synthetic Checking"}, "transactions": self.transactions,
        }]}
        return self.client.sandbox_public_token_create(SandboxPublicTokenCreateRequest(
            institution_id=INSTITUTION,
            initial_products=[Products("transactions")],
            options=SandboxPublicTokenCreateRequestOptions(
                override_username="user_custom",
                override_password=json.dumps(user),
                transactions=SandboxPublicTokenCreateRequestOptionsTransactions(days_requested=400),
            ),
        )).public_token

    def finish_auth(self, params: dict) -> Connection:
        token = self.client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=params["public_token"])
        ).access_token
        try:
            self.revoke()  # reconnect: don't orphan the previous sandbox Item (only once the new one exists)
        except Exception as e:  # noqa: BLE001 - cleanup must never cost the new connection
            log.warning("plaid: removing previous item failed (%s)", type(e).__name__)  # no body: no token
        finally:
            self._access_token = token
        return Connection(id=f"bank-{uuid.uuid4().hex[:8]}", provider="bank", status="connected",
                          scopes=["transactions"], connected_at=datetime.now(UTC))

    def fetch_since(self, cursor: str | None) -> tuple[list[RawItem], str]:
        """Blocking: the first sync can wait up to HISTORY_WAIT_S for sandbox history.

        Call it off the event loop (asyncio.to_thread). The access token lives in memory only,
        so a restart drops the connection; reset the demo after the last deploy.
        """
        if not self._access_token:
            raise RuntimeError("not connected")
        start, deadline, last_count = cursor, time.monotonic() + HISTORY_WAIT_S, -1
        while True:
            txns, removed, cursor = [], 0, start
            try:
                while True:
                    r = self.client.transactions_sync(TransactionsSyncRequest(
                        access_token=self._access_token, **({"cursor": cursor} if cursor else {})))
                    txns += list(r.added) + list(r.modified)
                    removed += len(r.removed)
                    cursor = r.next_cursor
                    if not r.has_more:
                        break
            except plaid.ApiException as e:
                if MUTATION in str(e.body or "") and time.monotonic() < deadline:
                    time.sleep(1)
                    continue  # Plaid: restart the whole pagination from the original cursor
                raise
            # First sync: re-pull until history is in AND the count holds across two reads. The
            # sandbox reports HISTORICAL_UPDATE_COMPLETE a few seconds before every txn is readable
            # (seen live: 0 or 9 of 25, then 25). After the deadline, return what we have.
            # A stable 0 doesn't count (live reads gave 0 after "complete"), so an empty account
            # waits the full deadline; fine for the planted demo account.
            history_done = str(r.transactions_update_status) == "HISTORICAL_UPDATE_COMPLETE"
            settled = history_done and len(txns) == last_count and txns
            if start is None and not settled and time.monotonic() < deadline:
                last_count = len(txns)
                time.sleep(SETTLE_S)
                continue
            break
        if removed:
            # ponytail: removed posted txns dropped; needs a contract change if P2 wants deletes
            log.info("plaid sync: %d removed transactions not propagated", removed)
        return [to_raw_item(t) for t in txns if not t.pending], cursor  # pending skipped (P2: ignored)

    def revoke(self) -> None:
        if self._access_token:
            token, self._access_token = self._access_token, None
            self.client.item_remove(ItemRemoveRequest(access_token=token))
