"""Maya's calendar events from the persona spec, and a writer that puts them in the demo calendar.

Every seeded event carries a private tag, so --clear removes only what the seeder wrote and
never touches anything else in the account's calendar.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

from backend.app.connectors.google_oauth import GoogleAuthError, GoogleOAuth
from backend.app.seed.persona import Persona

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
TAG = {"anchorpoint_seed": "1"}
RETRIES = 5


@dataclass(frozen=True)
class SeedEvent:
    title: str
    start: date
    end: date  # inclusive; Google's all-day end is exclusive, the writer adds the day


def events(persona: Persona) -> list[SeedEvent]:
    """The persona's `calendar:` section -> dated all-day events, oldest first."""
    found: list[SeedEvent] = []
    for spec in persona.spec.get("calendar", []):
        target = spec["for_each"]
        if target == "trips":
            for depart, _return in persona.trips():
                found.append(SeedEvent(spec["title"], depart, depart))  # on: depart
            continue
        ids = list(persona.assignments) if target == "assignments" else target
        for assignment_id in ids:
            facility = persona.assignments[assignment_id]["facility"]
            title = spec["title"].format(facility=facility)
            start, end = persona.start(assignment_id), persona.end(assignment_id)
            if spec.get("span") == "assignment":
                found.append(SeedEvent(title, start, end))
            else:
                # YAML 1.1 reads the bare key `on:` as the boolean True, so look up both
                when = spec.get("on", spec.get(True))
                day = start if when == "start" else end
                found.append(SeedEvent(title, day, day))
    return sorted(found, key=lambda event: (event.start, event.title))


class CalendarWriter:
    def __init__(self, oauth: GoogleOAuth) -> None:
        self.oauth = oauth

    def insert(self, event: SeedEvent) -> str:
        body = {
            "summary": event.title,
            "start": {"date": event.start.isoformat()},
            "end": {"date": (event.end + timedelta(days=1)).isoformat()},
            "transparency": "transparent",
            "extendedProperties": {"private": TAG},
        }
        return self._send("POST", API, body)["id"]

    def insert_all(self, seed: list[SeedEvent]) -> list[str]:
        return [self.insert(event) for event in seed]

    def clear(self) -> int:
        """Delete every event the seeder wrote earlier (tagged). Returns how many."""
        ids, page_token = [], None
        while True:
            params = {"privateExtendedProperty": "anchorpoint_seed=1", "maxResults": 250, "showDeleted": "false"}
            if page_token:
                params["pageToken"] = page_token
            page = self.oauth.get(API, params)
            ids += [event["id"] for event in page.get("items", [])]
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        for event_id in ids:
            self._send("DELETE", f"{API}/{urllib.parse.quote(event_id)}", None)
        return len(ids)

    def _send(self, method: str, url: str, payload: dict | None) -> dict:
        for attempt in range(1, RETRIES + 1):
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode() if payload is not None else None,
                method=method,
                headers={"Authorization": f"Bearer {self.oauth.access_token()}",
                         "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read()
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 429, 500, 503) and attempt < RETRIES:
                    time.sleep(2 ** attempt)  # rate limit or a transient Google error
                    continue
                detail = exc.read().decode("utf-8", "replace")[:300]
                raise GoogleAuthError(f"Calendar returned HTTP {exc.code}: {detail}", status=exc.code) from None
            except urllib.error.URLError as exc:
                raise GoogleAuthError(f"Could not reach Google: {exc.reason}") from None
        raise GoogleAuthError("Calendar request kept failing")
