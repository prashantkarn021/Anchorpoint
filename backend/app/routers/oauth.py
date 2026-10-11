"""Google OAuth: start the Gmail connection and receive Google's redirect."""

import logging
import os
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from backend.app.connectors.gmail import GmailConnector
from backend.app.connectors.google_oauth import GoogleAuthError
from backend.app.vault.tokens import VaultError, default_vault

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def gmail_connector() -> GmailConnector:
    try:
        return GmailConnector(default_vault())
    except VaultError as exc:
        log.warning("token vault unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from None


Gmail = Annotated[GmailConnector, Depends(gmail_connector)]


def _frontend(path: str) -> RedirectResponse:
    # Empty on the server (same origin behind Caddy); http://localhost when the api runs on :8000.
    return RedirectResponse(f"{os.getenv('FRONTEND_URL', '').rstrip('/')}{path}", status_code=303)


@router.post("/connections/gmail/start")
def start_gmail(connector: Gmail) -> dict:
    try:
        return {"redirect_url": connector.start_auth()}
    except (GoogleAuthError, VaultError) as exc:
        log.warning("gmail start failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.get("/oauth/callback")
def oauth_callback(request: Request, connector: Gmail):
    """Google sends the browser here. State is "<provider>.<nonce>"; only gmail exists so far."""
    params = dict(request.query_params)
    if params.get("error"):
        # Google's own short code (access_denied, ...), trimmed to a safe alphabet for the UI.
        code = re.sub(r"[^a-z_]", "", params["error"].lower())[:40] or "connection_failed"
        return _frontend(f"/connections?error={code}")
    if params.get("state", "").split(".", 1)[0] != "gmail":
        return _frontend("/connections?error=unknown_provider")
    try:
        connector.finish_auth(params)
    except (GoogleAuthError, VaultError) as exc:
        log.warning("gmail callback failed: %s", exc)  # exc never carries a token
        return _frontend("/connections?error=connection_failed")
    return _frontend("/connections?connected=gmail")
