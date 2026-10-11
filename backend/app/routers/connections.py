"""Connections as they really are: status, connect the bank, revoke."""

import logging
import os
import threading
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.connectors.calendar import CalendarConnector
from backend.app.connectors.gmail import GmailConnector
from backend.app.ledger import Ledger
from backend.app.models import Connection
from backend.app.routers import sync
from backend.app.routers.records import get_ledger
from backend.app.seed.bank import bank_transactions
from backend.app.seed.persona import Persona
from backend.app.sync import bank_session
from backend.app.vault.tokens import VaultError, default_vault

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

BANK_SCOPES = ["transactions (read-only)"]


def _gmail() -> GmailConnector | None:
    """The Gmail connector if an account is connected, else None."""
    try:
        connector = GmailConnector(default_vault())
    except VaultError:
        return None
    return connector if connector.oauth.is_connected() else None


def _calendar() -> CalendarConnector | None:
    """The Calendar connector if an account is connected, else None."""
    try:
        connector = CalendarConnector(default_vault())
    except VaultError:
        return None
    return connector if connector.oauth.is_connected() else None


def _google(provider: str) -> GmailConnector | CalendarConnector | None:
    return {"gmail": _gmail, "calendar": _calendar}.get(provider, lambda: None)()


def _connection(provider: str, scopes: list[str], since: datetime | None, ledger: Ledger) -> Connection:
    last_sync = sync.last_sync(provider)
    return Connection(
        id=provider,
        provider=provider,
        status="syncing" if sync.is_running() else "connected",
        scopes=scopes,
        connected_at=since or last_sync or datetime.now(UTC),
        last_sync=last_sync,
        items_seen=sync.items_seen(provider),
        records_created=len(ledger.list_records(provider=provider)),
    )


@router.get("/connections", response_model=list[Connection])
def connections(ledger: Annotated[Ledger, Depends(get_ledger)]) -> list[Connection]:
    """Only what is connected right now. A provider that is absent shows as "Not connected"."""
    found = []
    gmail = _gmail()
    if gmail is not None:
        found.append(_connection("gmail", gmail.oauth.granted_scopes(), None, ledger))
    calendar = _calendar()
    if calendar is not None:
        found.append(_connection("calendar", calendar.oauth.granted_scopes(), None, ledger))
    if bank_session.current() is not None:
        found.append(_connection("bank", BANK_SCOPES, bank_session.connected_at(), ledger))
    return found


def connect_bank(ledger: Ledger) -> None:
    """Fresh sandbox Item with the demo persona's transactions, replacing any earlier bank data.

    A new Item hands out new transaction ids, so records from the old one would otherwise
    stay behind as duplicates.
    """
    persona = Persona.load(os.getenv("DEMO_PERSONA", "maya"))
    with sync.paused():
        bank_session.connect(bank_transactions(persona))
        ledger.clear(provider="bank")
        sync.forget("bank")


def sync_in_background() -> None:
    def run() -> None:
        try:
            sync.run_sync()
        except Exception as exc:  # noqa: BLE001 -- nothing is waiting on this thread
            log.warning("background sync failed: %s", type(exc).__name__)

    threading.Thread(target=run, name="connect-sync", daemon=True).start()


@router.post("/connections/bank/start")
def start_bank(ledger: Annotated[Ledger, Depends(get_ledger)]) -> dict:
    """Sandbox shortcut: no Link screen, the Item is created server-side. No redirect needed."""
    try:
        connect_bank(ledger)
    except TimeoutError:
        raise HTTPException(status_code=409, detail="A sync is still running; try again shortly") from None
    except Exception as exc:  # noqa: BLE001 -- Plaid SDK errors, or missing keys
        log.warning("bank connect failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="The bank sandbox is not available") from None
    sync_in_background()  # the first read waits for Plaid's history, so it must not hold the request
    return {"redirect_url": None, "link_token": None}


class Revoke(BaseModel):
    delete_data: bool = False


@router.post("/connections/{provider}/revoke", response_model=Connection)
def revoke(provider: str, ledger: Annotated[Ledger, Depends(get_ledger)], body: Revoke | None = None) -> Connection:
    """Withdraw access at the provider and drop our tokens; optionally delete what was read."""
    gmail = _google(provider)  # gmail or calendar: both are Google grants revoked the same way
    if gmail is None and not (provider == "bank" and bank_session.current() is not None):
        raise HTTPException(status_code=404, detail="Connection not found")
    scopes = gmail.oauth.granted_scopes() if gmail else BANK_SCOPES
    since = None if gmail else bank_session.connected_at()
    try:
        with sync.paused():
            before = _connection(provider, scopes, since, ledger)
            if gmail is not None:
                gmail.revoke()
            else:
                bank_session.disconnect()
            if body is not None and body.delete_data:
                ledger.clear(provider=provider)
                sync.forget(provider)
    except TimeoutError:
        raise HTTPException(status_code=409, detail="A sync is still running; try again shortly") from None
    return before.model_copy(update={
        "status": "revoked",
        "records_created": len(ledger.list_records(provider=provider)),
    })
