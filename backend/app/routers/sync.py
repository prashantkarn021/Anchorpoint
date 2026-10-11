"""Run syncs: POST /api/sync on demand, plus a background poll while the app is up."""

import logging
import os
import threading
from functools import cache

from fastapi import APIRouter, HTTPException
from pydantic import TypeAdapter

from backend.app.connectors.gmail import GmailConnector
from backend.app.connectors.google_oauth import GoogleAuthError
from backend.app.ledger import Ledger
from backend.app.models import Profile
from backend.app.routers.stubs import load_fixture
from backend.app.sync.ingest import SyncResult, sync_gmail
from backend.app.sync.state import SyncState
from backend.app.vault.tokens import VaultError, database_path, default_vault

log = logging.getLogger(__name__)

POLL_SECONDS = int(os.getenv("SYNC_INTERVAL_S", "60"))  # 0 turns the background poll off
WAIT_FOR_RUNNING_SYNC_S = 120

_running = threading.Lock()  # one sync at a time; the model budget is per sync
_stop = threading.Event()


def _poll() -> None:
    while not _stop.wait(POLL_SECONDS):
        try:
            run_sync()
        except Exception as exc:  # noqa: BLE001 -- the poll must outlive any one bad sync
            log.warning("background sync failed: %s", type(exc).__name__)


def _start_poll() -> None:
    if POLL_SECONDS > 0:
        _stop.clear()
        threading.Thread(target=_poll, name="sync-poll", daemon=True).start()


router = APIRouter(prefix="/api", on_startup=[_start_poll], on_shutdown=[_stop.set])


@cache
def _ledger() -> Ledger:
    return Ledger(database_path())


@cache
def _state() -> SyncState:
    return SyncState(database_path())


def _profile() -> Profile:
    return load_fixture("profile.json", TypeAdapter(Profile))


def run_sync() -> list[SyncResult]:
    """Sync every connected provider once. Waits if a sync is already running."""
    if not _running.acquire(timeout=WAIT_FOR_RUNNING_SYNC_S):
        raise TimeoutError("a sync is still running")
    try:
        results = []
        gmail = GmailConnector(default_vault())
        if gmail.oauth.is_connected():
            results.append(sync_gmail(gmail, _ledger(), _state(), _profile()))
        return results
    finally:
        _running.release()


@router.post("/sync")
def sync() -> dict:
    try:
        results = run_sync()
    except TimeoutError:
        raise HTTPException(status_code=409, detail="A sync is still running; try again shortly") from None
    except (GoogleAuthError, VaultError) as exc:
        log.warning("sync failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not reach a connected account") from None
    return {"results": [result.model_dump() for result in results]}
