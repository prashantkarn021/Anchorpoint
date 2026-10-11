"""Demo controls: inject a fresh synthetic email, or reset the ledger and read everything again."""

import logging
import os
import threading
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.app.connectors.gmail import API, GmailConnector
from backend.app.connectors.google_oauth import GoogleAuthError, GoogleOAuth
from backend.app.ledger import Ledger
from backend.app.routers import sync
from backend.app.routers.records import get_ledger, seed_fixtures
from backend.app.seed.emails import CENTRAL, inject_emails
from backend.app.seed.gmail_writer import GmailWriter
from backend.app.seed.persona import Persona
from backend.app.vault.tokens import VaultError, default_vault

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/demo")

# Insert-only: this grant can add a message to the inbox but cannot read, send or delete.
INSERT_SCOPES = ["https://www.googleapis.com/auth/gmail.insert"]


def inject_writer() -> GmailWriter:
    """Writer on the seeder client's grant, which is separate from the app's read-only one."""
    client_id = os.getenv("SEED_GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("SEED_GOOGLE_CLIENT_SECRET", "")
    try:
        if not (client_id and client_secret):
            raise VaultError("SEED_GOOGLE_CLIENT_ID and SEED_GOOGLE_CLIENT_SECRET are not set")
        oauth = GoogleOAuth(
            "seed", INSERT_SCOPES, default_vault(), client_id=client_id, client_secret=client_secret
        )
        if not oauth.is_connected():
            raise VaultError("the demo injector has not been granted access to the inbox")
    except VaultError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return GmailWriter(oauth)


def inbox_address() -> str:
    """Who the email is addressed to. Cosmetic: the insert goes to the granted inbox either way."""
    try:
        return GmailConnector(default_vault()).oauth.get(f"{API}/profile")["emailAddress"]
    except (GoogleAuthError, VaultError, KeyError):
        return os.getenv("DEMO_GMAIL_ADDRESS", "demo@anchorpoint.example")


@router.post("/inject")
def inject(
    writer: Annotated[GmailWriter, Depends(inject_writer)],
    address: Annotated[str, Depends(inbox_address)],
) -> dict:
    persona = Persona.load(os.getenv("DEMO_PERSONA", "maya"))
    emails = inject_emails(persona, datetime.now(CENTRAL))
    try:
        ids = [writer.insert(email, persona.profile["name"], address) for email in emails]
    except GoogleAuthError as exc:
        log.warning("demo inject failed: %s", exc)
        raise HTTPException(status_code=502, detail="Gmail did not accept the email") from None
    return {
        "inserted": len(ids),
        "emails": [
            {"source_id": message_id, "from": email.sender_name, "subject": email.subject}
            for message_id, email in zip(ids, emails, strict=True)
        ],
    }


def _sync_in_background() -> None:
    def run() -> None:
        try:
            sync.run_sync()
        except Exception as exc:  # noqa: BLE001 -- nothing is waiting on this thread
            log.warning("sync after reset failed: %s", type(exc).__name__)

    threading.Thread(target=run, name="reset-sync", daemon=True).start()


@router.post("/reset")
def reset(ledger: Annotated[Ledger, Depends(get_ledger)]) -> dict:
    """Empty the ledger and the sync's memory, then read every connected account again.

    Connections survive: tokens live in the vault, which this does not touch. The refill runs
    in the background, so records reappear over the next seconds instead of holding the request.
    """
    try:
        with sync.paused():  # a sync mid-run would write into the ledger we are emptying
            records, events = ledger.clear()
            sync.forget()
            seeded = seed_fixtures(ledger)
    except TimeoutError:
        raise HTTPException(status_code=409, detail="A sync is still running; try again shortly") from None
    _sync_in_background()
    return {"cleared": {"records": records, "events": events}, "fixtures_loaded": seeded, "sync": "started"}
