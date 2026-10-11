"""Run syncs: POST /api/sync on demand, plus a background poll while the app is up."""

import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime
from functools import cache

from fastapi import APIRouter, HTTPException
from pydantic import TypeAdapter

from backend.app.connectors.calendar import CalendarConnector
from backend.app.connectors.gmail import GmailConnector
from backend.app.connectors.google_oauth import GoogleAuthError
from backend.app.ledger import Ledger
from backend.app.models import Profile
from backend.app.routers.stubs import load_fixture
from backend.app.sync import bank_session
from backend.app.sync.ingest import SyncResult, sync_bank, sync_calendar, sync_gmail
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


@contextmanager
def paused():
    """Hold syncing off while the caller changes the ledger. Raises TimeoutError if one won't finish."""
    if not _running.acquire(timeout=WAIT_FOR_RUNNING_SYNC_S):
        raise TimeoutError("a sync is still running")
    try:
        yield
    finally:
        _running.release()


def forget(provider: str | None = None) -> None:
    """Drop cursors and finished items (for one provider, or all), so the next sync reads again."""
    _state().clear(provider)


def is_running() -> bool:
    return _running.locked()


def last_sync(provider: str) -> datetime | None:
    stamp = _state().last_sync(provider)
    return datetime.fromisoformat(stamp) if stamp else None


def items_seen(provider: str) -> int:
    return len(_state().seen(provider))


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
        calendar = CalendarConnector(default_vault())
        if calendar.oauth.is_connected():
            try:
                results.append(sync_calendar(calendar, _ledger(), _state(), _profile()))
            except GoogleAuthError as exc:  # a calendar problem must not stop the bank sync
                log.warning("calendar sync failed: %s", exc)
                if exc.status == 410:  # updatedMin too long ago: start a fresh backfill
                    _state().set_cursor("calendar", None)
        bank = bank_session.current()
        if bank is not None:
            results.append(sync_bank(bank, _ledger(), _state(), _profile()))
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
    except Exception as exc:  # noqa: BLE001 -- Plaid SDK errors carry request bodies; log the type only
        log.warning("sync failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Could not reach a connected account") from None
    return {"results": [result.model_dump() for result in results]}
