"""The activity feed: recent audit events, and a live stream of new ones (SSE)."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sse_starlette.sse import EventSourceResponse

from backend.app.ledger import Ledger
from backend.app.models import AuditEvent
from backend.app.routers.records import get_ledger

router = APIRouter(prefix="/api")

POLL_SECONDS = 1.0  # how often the stream looks for new events
BATCH = 200

Feed = Annotated[Ledger, Depends(get_ledger)]


def _event(row: dict) -> AuditEvent:
    return AuditEvent.model_validate({key: row[key] for key in ("ts", "actor", "action", "record_id", "detail")})


def latest_id(ledger: Ledger) -> int:
    rows = ledger.list_events(limit=1)
    return rows[0]["id"] if rows else 0


def events_after(ledger: Ledger, last_id: int) -> list[tuple[int, AuditEvent]]:
    """Events newer than `last_id`, oldest first, each with its id."""
    return [(row["id"], _event(row)) for row in ledger.list_events(limit=BATCH, after_id=last_id)]


@router.get("/activity", response_model=list[AuditEvent])
def activity(ledger: Feed, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[AuditEvent]:
    """Most recent events first."""
    return [_event(row) for row in ledger.list_events(limit=limit)]


@router.get("/activity/stream")
async def activity_stream(request: Request, ledger: Feed) -> EventSourceResponse:
    """New events as they are written. History comes from GET /activity; a reconnecting
    browser sends Last-Event-ID and picks up where it left off."""
    resume = request.headers.get("last-event-id", "")
    last_id = int(resume) if resume.isdigit() else await asyncio.to_thread(latest_id, ledger)

    async def stream():
        nonlocal last_id
        while not await request.is_disconnected():
            for event_id, event in await asyncio.to_thread(events_after, ledger, last_id):
                last_id = event_id
                yield {"id": str(event_id), "data": event.model_dump_json()}
            await asyncio.sleep(POLL_SECONDS)

    return EventSourceResponse(stream(), ping=15)
