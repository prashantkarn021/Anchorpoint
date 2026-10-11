import base64
import time
from urllib.parse import parse_qs, urlparse

import pytest

from backend.app.connectors import gmail
from backend.app.connectors.gmail import API, BACKFILL_WINDOW, GmailConnector
from backend.app.connectors.google_oauth import REVOKE_URL, TOKEN_URL, GoogleAuthError

CONFIG = {
    "client_id": "client-id",
    "client_secret": "client-secret",
    "redirect_uri": "http://localhost:8000/api/oauth/callback",
}


class MemoryStore:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)


class FakeGoogle:
    """Stands in for Google's HTTP API and records every call."""

    def __init__(self, messages=None):
        self.calls = []
        self.messages = {message["id"]: message for message in messages or []}
        self.token_reply = {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
        }

    def __call__(self, method, url, params, form, token):
        self.calls.append((method, url, params, form, token))
        if url == TOKEN_URL:
            return self.token_reply
        if url == REVOKE_URL:
            return {}
        if url == f"{API}/messages":
            return {"messages": [{"id": message_id} for message_id in self.messages]}
        if "/attachments/" in url:
            return {"data": b64("attached text")}
        return self.messages[url.rsplit("/", 1)[-1]]


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def message(message_id, epoch_s, subject, body, attachment=None):
    parts = [{"mimeType": "text/plain", "body": {"data": b64(body)}}]
    if attachment:
        parts.append(
            {
                "mimeType": "text/plain",
                "filename": attachment,
                "body": {"attachmentId": "att-1", "size": 13},
            }
        )
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "internalDate": str(epoch_s * 1000),
        "labelIds": ["INBOX"],
        "snippet": "Your bill is ready &amp; waiting",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "Evergreen Power & Light <billing@evergreenpl.example>"},
                {"name": "Subject", "value": subject},
            ],
            "parts": parts,
        },
    }


def connected(google):
    store = MemoryStore()
    connector = GmailConnector(store, google, **CONFIG)
    state = parse_qs(urlparse(connector.start_auth()).query)["state"][0]
    connector.finish_auth({"code": "auth-code", "state": state})
    return connector, store


def test_start_auth_asks_for_read_only_offline_access():
    connector = GmailConnector(MemoryStore(), FakeGoogle(), **CONFIG)

    query = parse_qs(urlparse(connector.start_auth()).query)

    assert query["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["redirect_uri"] == [CONFIG["redirect_uri"]]
    assert query["state"][0].startswith("gmail.")
    assert "include_granted_scopes" not in query


def test_start_auth_needs_client_config(monkeypatch):
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "OAUTH_REDIRECT_URI"):
        monkeypatch.delenv(name, raising=False)
    connector = GmailConnector(MemoryStore(), FakeGoogle())

    with pytest.raises(GoogleAuthError):
        connector.start_auth()


def test_finish_auth_exchanges_code_and_stores_tokens():
    google = FakeGoogle()
    _, store = connected(google)

    assert store.get("gmail:tokens")["refresh_token"] == "refresh-1"
    assert store.get("gmail:state") is None
    form = google.calls[-1][3]
    assert form["code"] == "auth-code"
    assert form["grant_type"] == "authorization_code"


def test_finish_auth_returns_connected_connection():
    store = MemoryStore()
    connector = GmailConnector(store, FakeGoogle(), **CONFIG)
    state = parse_qs(urlparse(connector.start_auth()).query)["state"][0]

    connection = connector.finish_auth({"code": "auth-code", "state": state})

    assert connection.provider == "gmail"
    assert connection.status == "connected"
    assert connection.scopes == ["https://www.googleapis.com/auth/gmail.readonly"]


def test_finish_auth_rejects_wrong_state():
    store = MemoryStore()
    connector = GmailConnector(store, FakeGoogle(), **CONFIG)
    connector.start_auth()

    with pytest.raises(GoogleAuthError):
        connector.finish_auth({"code": "auth-code", "state": "gmail.forged"})
    assert store.get("gmail:tokens") is None


def test_finish_auth_rejects_non_ascii_state_without_crashing():
    connector = GmailConnector(MemoryStore(), FakeGoogle(), **CONFIG)
    connector.start_auth()

    with pytest.raises(GoogleAuthError):
        connector.finish_auth({"code": "auth-code", "state": "gmail.é中"})


def test_finish_auth_rejects_callback_without_start():
    connector = GmailConnector(MemoryStore(), FakeGoogle(), **CONFIG)

    with pytest.raises(GoogleAuthError):
        connector.finish_auth({"code": "auth-code", "state": ""})


def test_finish_auth_reports_denied_consent():
    connector = GmailConnector(MemoryStore(), FakeGoogle(), **CONFIG)
    connector.start_auth()

    with pytest.raises(GoogleAuthError, match="access_denied"):
        connector.finish_auth({"error": "access_denied"})


def test_fetch_since_backfill_returns_raw_items_oldest_first():
    google = FakeGoogle(
        [
            message("m2", 1_760_000_200, "Your bill is ready", "Amount due $87.42"),
            message("m1", 1_760_000_100, "Rent payment received", "We received $1,150.00"),
        ]
    )
    connector, _ = connected(google)

    items, cursor = connector.fetch_since(None)

    assert [item.source_id for item in items] == ["m1", "m2"]
    assert cursor == "1760000200"
    first = items[0]
    assert first.provider == "gmail"
    assert "Subject: Rent payment received" in first.text
    assert "We received $1,150.00" in first.text
    assert first.meta["subject"] == "Rent payment received"
    assert first.meta["snippet"] == "Your bill is ready & waiting"
    assert first.meta["deep_link"].endswith("/m1")
    list_call = next(call for call in google.calls if call[1] == f"{API}/messages")
    assert list_call[2]["q"].endswith(BACKFILL_WINDOW)
    assert list_call[4] == "access-1"


def test_fetch_since_uses_cursor_and_keeps_it_when_nothing_is_new():
    google = FakeGoogle()
    connector, _ = connected(google)

    items, cursor = connector.fetch_since("1760000200")

    assert items == []
    assert cursor == "1760000200"
    assert google.calls[-1][2]["q"].endswith("after:1760000200")


def test_fetch_since_over_the_cap_takes_the_oldest_and_stops_the_cursor_there(monkeypatch):
    monkeypatch.setattr(gmail, "MAX_ITEMS", 2)
    google = FakeGoogle(  # Gmail lists newest first
        [message(f"m{n}", 1_760_000_000 + n, "Statement", "body") for n in (4, 3, 2, 1)]
    )
    connector, _ = connected(google)

    items, cursor = connector.fetch_since(None)

    assert [item.source_id for item in items] == ["m1", "m2"]
    assert cursor == "1760000002"


def test_fetch_since_extracts_text_attachments():
    google = FakeGoogle([message("m1", 1_760_000_100, "Statement", "See attached", "bill.txt")])
    connector, _ = connected(google)

    items, _ = connector.fetch_since(None)

    attachment = items[0].attachments[0]
    assert attachment.filename == "bill.txt"
    assert attachment.text_extracted == "attached text"
    assert items[0].meta["attachment_ids"] == {"bill.txt": "att-1"}


def test_expired_access_token_is_refreshed_and_refresh_token_kept():
    google = FakeGoogle()
    connector, store = connected(google)
    tokens = store.get("gmail:tokens")
    store.set("gmail:tokens", {**tokens, "expires_at": time.time() - 10})
    google.token_reply = {"access_token": "access-2", "expires_in": 3600}

    connector.fetch_since(None)

    assert store.get("gmail:tokens")["access_token"] == "access-2"
    assert store.get("gmail:tokens")["refresh_token"] == "refresh-1"
    assert google.calls[-1][4] == "access-2"


def test_fetch_without_connection_fails():
    connector = GmailConnector(MemoryStore(), FakeGoogle(), **CONFIG)

    with pytest.raises(GoogleAuthError, match="not connected"):
        connector.fetch_since(None)


def test_revoke_tells_google_and_drops_tokens():
    google = FakeGoogle()
    connector, store = connected(google)

    connector.revoke()

    assert store.get("gmail:tokens") is None
    assert google.calls[-1][1] == REVOKE_URL
    assert google.calls[-1][3] == {"token": "refresh-1"}
