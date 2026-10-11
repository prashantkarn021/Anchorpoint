"""Write synthetic emails into the demo Gmail inbox.

Uses the seeder OAuth client, which holds gmail.modify. The app's own client is
read-only and must never be given this scope.
"""

import base64
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import format_datetime, formataddr

from backend.app.connectors.google_oauth import GoogleAuthError, GoogleOAuth
from backend.app.seed.emails import SeedEmail

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
API = "https://gmail.googleapis.com/gmail/v1/users/me"
WORKERS = 6
RETRIES = 5


def to_mime(email: SeedEmail, to_name: str, to_address: str) -> bytes:
    message = EmailMessage()
    message["From"] = formataddr((email.sender_name, email.sender_email))
    message["To"] = formataddr((to_name, to_address))
    message["Subject"] = email.subject
    message["Date"] = format_datetime(email.sent_at)
    message["Message-ID"] = f"<{email.key}@{email.sender_email.split('@')[1]}>"
    message.set_content(email.body)
    for filename, mime_type, data in email.attachments:
        maintype, subtype = mime_type.split("/")
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    if message.is_multipart():
        message.set_boundary(f"=={email.key}==")  # the default is random; keep re-seeds identical
    return message.as_bytes()


class GmailWriter:
    def __init__(self, oauth: GoogleOAuth) -> None:
        self.oauth = oauth

    def address(self) -> str:
        return self.oauth.get(f"{API}/profile")["emailAddress"]

    def insert(self, email: SeedEmail, to_name: str, to_address: str) -> str:
        """Add one message to the inbox, dated by its Date header. Returns the Gmail id."""
        raw = base64.urlsafe_b64encode(to_mime(email, to_name, to_address)).decode()
        reply = self._post(
            f"{API}/messages?internalDateSource=dateHeader",
            {"raw": raw, "labelIds": ["INBOX", "UNREAD"]},
        )
        return reply["id"]

    def insert_all(self, emails: list[SeedEmail], to_name: str, to_address: str) -> list[str]:
        self.oauth.access_token()  # refresh once up front, not once per worker
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            return list(pool.map(lambda email: self.insert(email, to_name, to_address), emails))

    def clear(self) -> int:
        """Move every message in the mailbox to the trash. Returns how many."""
        ids, page_token = [], None
        while True:
            params = {"maxResults": 500, "q": "-in:trash -in:spam"}
            if page_token:
                params["pageToken"] = page_token
            page = self.oauth.get(f"{API}/messages", params)
            ids += [message["id"] for message in page.get("messages", [])]
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            list(pool.map(lambda message_id: self._post(f"{API}/messages/{message_id}/trash", {}), ids))
        return len(ids)

    def _post(self, url: str, payload: dict) -> dict:
        for attempt in range(1, RETRIES + 1):
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.oauth.access_token()}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.loads(response.read() or b"{}")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                # Gmail's per-user quota is easy to hit when inserting in parallel.
                throttled = exc.code in (429, 500, 503) or "rateLimit" in detail
                if throttled and attempt < RETRIES:
                    time.sleep(1.5 * attempt)
                    continue
                raise GoogleAuthError(f"Gmail returned HTTP {exc.code}: {detail}") from None
            except urllib.error.URLError as exc:
                raise GoogleAuthError(f"Could not reach Gmail: {exc.reason}") from None
        raise GoogleAuthError("Gmail kept throttling the request")
