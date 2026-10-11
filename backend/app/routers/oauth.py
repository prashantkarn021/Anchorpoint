"""Google OAuth: start the Gmail and Calendar connections and receive Google's redirect."""

import logging
import os
import re
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from backend.app.connectors.calendar import CalendarConnector
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


def calendar_connector() -> CalendarConnector:
    try:
        return CalendarConnector(default_vault())
    except VaultError as exc:
        log.warning("token vault unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from None


def calendar_factory():
    """Built only when a calendar callback arrives, so a Gmail callback never needs it."""
    return calendar_connector


Calendar = Annotated[CalendarConnector, Depends(calendar_connector)]
CalendarFactory = Annotated[Callable[[], CalendarConnector], Depends(calendar_factory)]


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


@router.post("/connections/calendar/start")
def start_calendar(connector: Calendar) -> dict:
    try:
        return {"redirect_url": connector.start_auth()}
    except (GoogleAuthError, VaultError) as exc:
        log.warning("calendar start failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.get("/oauth/callback")
def oauth_callback(request: Request, connector: Gmail, make_calendar: CalendarFactory):
    """Google sends the browser here. State is "<provider>.<nonce>": gmail or calendar."""
    params = dict(request.query_params)
    if params.get("error"):
        # Google's own short code (access_denied, ...), trimmed to a safe alphabet for the UI.
        code = re.sub(r"[^a-z_]", "", params["error"].lower())[:40] or "connection_failed"
        return _frontend(f"/connections?error={code}")
    provider = params.get("state", "").split(".", 1)[0]
    if provider not in ("gmail", "calendar"):
        return _frontend("/connections?error=unknown_provider")
    try:
        (connector if provider == "gmail" else make_calendar()).finish_auth(params)
    except (GoogleAuthError, VaultError) as exc:
        log.warning("%s callback failed: %s", provider, exc)  # exc never carries a token
        return _frontend("/connections?error=connection_failed")
    except HTTPException:  # the vault is unavailable for the calendar connector
        return _frontend("/connections?error=connection_failed")
    return _frontend(f"/connections?connected={provider}")
