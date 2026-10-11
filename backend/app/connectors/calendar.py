"""Google Calendar connector: read-only OAuth, events as RawItems. No model ever reads them."""

import logging
from datetime import UTC, date, datetime, timedelta

from backend.app.connectors.google_oauth import GoogleOAuth, Http, TokenStore, http_json
from backend.app.models import Connection, RawItem

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
BACKFILL_DAYS = 400  # same history as Gmail and the bank: the rules look 12 full months back
PAGE_SIZE = 250
MAX_PAGES = 20  # hard stop; a demo calendar is a few dozen events
MAX_TITLE_CHARS = 200


def _when(value: dict) -> tuple[datetime, bool]:
    """Google gives all-day events a "date" and timed events a "dateTime".

    Timed events keep their own offset, so an evening flight is dated where it happened,
    not on the next UTC day.
    """
    if value.get("dateTime"):
        return datetime.fromisoformat(value["dateTime"]), False
    day = date.fromisoformat(value["date"])
    return datetime(day.year, day.month, day.day, tzinfo=UTC), True


def to_raw_item(event: dict) -> RawItem | None:
    """One event -> RawItem, or None for cancelled or undated events."""
    if event.get("status") == "cancelled" or not event.get("start"):
        return None
    start, all_day = _when(event["start"])
    end, _ = _when(event.get("end") or event["start"])
    if all_day:
        end -= timedelta(days=1)  # Google's all-day end date is exclusive
    title = " ".join(str(event.get("summary", "")).split())[:MAX_TITLE_CHARS]
    # Anyone can send an invite, and Google adds it to the calendar. Only events the user
    # created themselves count as their own evidence.
    own = bool((event.get("organizer") or {}).get("self") or (event.get("creator") or {}).get("self"))
    return RawItem(
        provider="calendar",
        source_id=event["id"],
        received_at=start.astimezone(UTC),
        text=title,
        meta={"title": title, "start": start.date().isoformat(), "end": end.date().isoformat(),
              "all_day": all_day, "own": own, "deep_link": event.get("htmlLink")},
    )


class CalendarConnector:
    provider = "calendar"

    def __init__(self, store: TokenStore, http: Http = http_json, **oauth_config: str) -> None:
        self.oauth = GoogleOAuth("calendar", SCOPES, store, http, **oauth_config)

    def start_auth(self) -> str:
        return self.oauth.start_auth()

    def finish_auth(self, params: dict) -> Connection:
        tokens = self.oauth.finish_auth(params)
        return Connection(
            id="calendar", provider="calendar", status="connected",
            scopes=str(tokens.get("scope", "")).split() or SCOPES, connected_at=datetime.now(UTC),
        )

    def fetch_since(self, cursor: str | None) -> tuple[list[RawItem], str]:
        """Events changed since the cursor (an RFC 3339 time), plus the new cursor.

        The first sync backfills BACKFILL_DAYS. Later syncs ask only for events updated
        since the last one; ingestion is idempotent on provider + source_id.
        """
        started = datetime.now(UTC)
        params = {"singleEvents": "true", "orderBy": "startTime", "maxResults": PAGE_SIZE,
                  "timeMin": (started - timedelta(days=BACKFILL_DAYS)).isoformat()}
        if cursor:
            params["updatedMin"] = cursor
        items: list[RawItem] = []
        for _ in range(MAX_PAGES):
            page = self.oauth.get(API, params)
            items += [item for item in map(to_raw_item, page.get("items", [])) if item is not None]
            if not page.get("nextPageToken"):
                break
            params = {**params, "pageToken": page["nextPageToken"]}
        else:
            # Not everything was read: keep the old cursor so the rest is fetched next time.
            log.warning("calendar sync: stopped after %d pages", MAX_PAGES)
            return items, cursor or ""
        return items, started.isoformat()

    def revoke(self) -> None:
        # Gmail and Calendar share one Google OAuth client, so revoking this token at Google
        # would withdraw Gmail's access too. Drop only our stored calendar token; revoking
        # Gmail (or the user's Google account page) removes the shared grant.
        self.oauth.store.delete(f"{self.oauth.provider}:tokens")
