import asyncio
import json
from datetime import UTC, datetime

import pytest
from sse_starlette.sse import AppStatus

from backend.app.ledger import Ledger
from backend.app.main import app
from backend.app.models import AuditEvent
from backend.app.routers import activity
from backend.app.routers.records import get_ledger


@pytest.mark.parametrize("resume", [True, False])
def test_sse_replays_in_order_and_delivers_new_events(tmp_path, monkeypatch, resume):
    ledger = Ledger(str(tmp_path / "stream.db"))

    def add(detail):
        ledger.add_event(AuditEvent(ts=datetime.now(UTC), actor="rules", action="risk_checked", detail=detail))

    add("old")
    last_id = activity.latest_id(ledger)
    if resume:
        for detail in ("one", "two", "three"):
            add(detail)
    monkeypatch.setattr(activity, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(activity, "BATCH", 2)  # replay crosses a page boundary
    monkeypatch.setattr(AppStatus, "should_exit", False)
    monkeypatch.setattr(AppStatus, "should_exit_event", None)
    app.dependency_overrides[get_ledger] = lambda: ledger

    async def request():
        done = asyncio.Event()
        messages = []

        async def receive():
            await done.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.start" and not resume:
                await asyncio.to_thread(add, "new")
            chunks = b"".join(m.get("body", b"") for m in messages)
            if chunks.count(b"data:") >= (3 if resume else 1):
                done.set()

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "GET", "scheme": "http", "path": "/api/activity/stream",
            "query_string": b"", "root_path": "", "server": ("test", 80), "client": ("test", 1),
            "headers": [(b"last-event-id", str(last_id).encode())] if resume else [],
        }
        await asyncio.wait_for(app(scope, receive, send), timeout=3)
        start = next(m for m in messages if m["type"] == "http.response.start")
        assert start["status"] == 200
        assert dict(start["headers"])[b"content-type"].startswith(b"text/event-stream")
        chunks = b"".join(m.get("body", b"") for m in messages).decode()
        events = [json.loads(line[6:]) for line in chunks.splitlines() if line.startswith("data: ")]
        ids = [int(line[4:]) for line in chunks.splitlines() if line.startswith("id: ")]
        assert [e["detail"] for e in events] == (["one", "two", "three"] if resume else ["new"])
        assert ids == list(range(last_id + 1, last_id + len(events) + 1))
        assert all(e["action"] == "risk_checked" for e in events)

    try:
        asyncio.run(request())
    finally:
        app.dependency_overrides.clear()
