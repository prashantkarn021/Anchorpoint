"""Demo controls. POST /api/demo/inject drops a fresh synthetic email into the demo inbox."""

import logging
import os
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.app.connectors.gmail import API, GmailConnector
from backend.app.connectors.google_oauth import GoogleAuthError, GoogleOAuth
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
