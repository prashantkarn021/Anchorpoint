"""Gmail connector: read-only OAuth, prefiltered fetch, messages as RawItems."""

import base64
import html
import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from backend.app.connectors.google_oauth import (
    GoogleAuthError,
    GoogleOAuth,
    Http,
    TokenStore,
    http_json,
)
from backend.app.models import Attachment, Connection, RawItem

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
API = "https://gmail.googleapis.com/gmail/v1/users/me"

# Deterministic prefilter (plan section 7): evidence-looking words or any attachment,
# minus the promotions and social tabs. Everything else never reaches the model.
KEYWORDS = (
    "receipt OR invoice OR statement OR lease OR rent OR itinerary OR "
    '"payment received" OR "your bill" OR assignment OR offer OR "per diem" OR '
    "renewal OR registration OR confirmation OR paystub OR bill"
)
PREFILTER = f"({KEYWORDS} OR has:attachment) -category:promotions -category:social"
# The rules look at the previous 12 *full* months, which reaches up to 13 months back, so
# 12 months would drop the oldest one. 400 days matches the bank connector's history.
BACKFILL_WINDOW = "newer_than:400d"

PAGE_SIZE = 25
MAX_ITEMS = 500          # hard cap per sync, protects the LLM budget downstream
MAX_LISTED = 5000        # ids are cheap to list; stop paging somewhere
MAX_TEXT_CHARS = 20_000
MAX_ATTACHMENT_BYTES = 5_000_000
FETCH_WORKERS = 8


class GmailConnector:
    provider = "gmail"

    def __init__(
        self,
        store: TokenStore,
        http: Http = http_json,
        query: str = PREFILTER,
        **oauth_config: str,
    ) -> None:
        self.oauth = GoogleOAuth("gmail", SCOPES, store, http, **oauth_config)
        self.query = query

    def start_auth(self) -> str:
        return self.oauth.start_auth()

    def finish_auth(self, params: dict) -> Connection:
        tokens = self.oauth.finish_auth(params)
        return Connection(
            id="gmail",
            provider="gmail",
            status="connected",
            scopes=str(tokens.get("scope", "")).split() or SCOPES,
            connected_at=datetime.now(UTC),
        )

    def fetch_since(self, cursor: str | None) -> tuple[list[RawItem], str]:
        """Messages newer than the cursor (epoch seconds), oldest first, plus the new cursor.

        The cursor's own second is fetched again on purpose so nothing landing in that
        second is missed; ingestion is idempotent on provider + source_id.

        At most MAX_ITEMS come back per call. When more are waiting, the oldest are
        returned and the cursor stops at the newest of those, so the next call picks
        up the rest instead of skipping them.
        """
        window = f"after:{cursor}" if cursor else BACKFILL_WINDOW
        ids = self._list_ids(f"{self.query} {window}".strip())
        if not ids:
            return [], cursor or "0"
        if len(ids) > MAX_ITEMS:
            log.warning("gmail sync: %d messages waiting, taking the oldest %d", len(ids), MAX_ITEMS)
            ids = ids[-MAX_ITEMS:]  # Gmail lists newest first
        token = self.oauth.access_token()

        def fetch(message_id: str) -> RawItem | None:
            try:
                return self._fetch_item(message_id, token)
            except GoogleAuthError as exc:
                if exc.status == 404:
                    return None
                raise

        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            items = [item for item in pool.map(fetch, ids) if item is not None]
        if not items:
            return [], cursor or "0"
        items.sort(key=lambda item: item.received_at)
        newest = int(items[-1].received_at.timestamp())
        return items, str(max(newest, int(cursor or 0)))

    def revoke(self) -> None:
        self.oauth.revoke()

    # --- internals ---------------------------------------------------------------

    def _list_ids(self, query: str) -> list[str]:
        ids: list[str] = []
        page_token = None
        while len(ids) < MAX_LISTED:
            params = {"q": query, "maxResults": PAGE_SIZE}
            if page_token:
                params["pageToken"] = page_token
            page = self.oauth.get(f"{API}/messages", params)
            ids.extend(message["id"] for message in page.get("messages", []))
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        return ids

    def _fetch_item(self, message_id: str, token: str) -> RawItem:
        message = self.oauth.http(
            "GET", f"{API}/messages/{message_id}", {"format": "full"}, None, token
        )
        payload = message.get("payload", {})
        headers = {
            header["name"].lower(): header["value"] for header in payload.get("headers", [])
        }
        parts = list(_walk(payload))
        body = _body_text(parts)
        head = "\n".join(
            f"{name.title()}: {headers[name]}"
            for name in ("from", "to", "subject", "date")
            if name in headers
        )
        attachment_parts = [part for part in parts if part.get("filename")]
        return RawItem(
            provider="gmail",
            source_id=message["id"],
            received_at=datetime.fromtimestamp(int(message["internalDate"]) / 1000, UTC),
            text=f"{head}\n\n{body}"[:MAX_TEXT_CHARS],
            attachments=[self._attachment(message_id, part) for part in attachment_parts],
            meta={
                "from": headers.get("from", ""),
                "to": headers.get("to", ""),
                "subject": headers.get("subject", ""),
                "thread_id": message.get("threadId"),
                "label_ids": message.get("labelIds", []),
                "snippet": html.unescape(message.get("snippet", "")),
                "deep_link": f"https://mail.google.com/mail/u/0/#all/{message['id']}",
                # lets the vision path fetch image bytes later without re-walking the message
                "attachment_ids": {
                    part["filename"]: part["body"]["attachmentId"]
                    for part in attachment_parts
                    if part.get("body", {}).get("attachmentId")
                },
            },
        )

    def _attachment(self, message_id: str, part: dict) -> Attachment:
        body = part.get("body", {})
        mime_type = part.get("mimeType", "application/octet-stream")
        size = int(body.get("size", 0))
        text = None
        wants_text = mime_type == "application/pdf" or mime_type.startswith("text/")
        if wants_text and size <= MAX_ATTACHMENT_BYTES:
            try:
                text = _extract_text(self._attachment_bytes(message_id, body), mime_type)
            except Exception:  # noqa: BLE001 -- a bad attachment must not sink the whole sync
                text = None
        return Attachment(
            filename=part["filename"], mime_type=mime_type, size_bytes=size, text_extracted=text
        )

    def _attachment_bytes(self, message_id: str, body: dict) -> bytes:
        if body.get("data"):
            return _b64(body["data"])
        if not body.get("attachmentId"):
            raise GoogleAuthError("attachment has no data")
        reply = self.oauth.get(f"{API}/messages/{message_id}/attachments/{body['attachmentId']}")
        return _b64(reply.get("data", ""))


def _walk(part: dict):
    yield part
    for child in part.get("parts", []):
        yield from _walk(child)


def _b64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _body_text(parts: list[dict]) -> str:
    """Prefer the plain-text body; fall back to the HTML body with tags stripped."""
    for wanted in ("text/plain", "text/html"):
        for part in parts:
            data = part.get("body", {}).get("data")
            if part.get("mimeType") == wanted and data and not part.get("filename"):
                text = _b64(data).decode("utf-8", "replace")
                return _strip_html(text) if wanted == "text/html" else text.strip()
    return ""


def _strip_html(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style).*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


def _extract_text(data: bytes, mime_type: str) -> str | None:
    if mime_type == "application/pdf":
        from pypdf import PdfReader  # imported here so the connector loads without it

        pages = PdfReader(io.BytesIO(data)).pages
        text = "\n".join(page.extract_text() or "" for page in pages).strip()
        return text[:MAX_TEXT_CHARS] or None
    return data.decode("utf-8", "replace")[:MAX_TEXT_CHARS] or None
