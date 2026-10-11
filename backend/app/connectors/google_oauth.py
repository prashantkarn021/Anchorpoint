"""Google OAuth and REST plumbing shared by the Gmail and Calendar connectors."""

import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Protocol

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Refresh this many seconds before the access token actually expires.
EXPIRY_MARGIN_S = 60


class GoogleAuthError(Exception):
    """OAuth or API failure. The message never contains a token or secret."""


class TokenStore(Protocol):
    """Where tokens live. The vault implements this; values must be encrypted at rest."""

    def get(self, key: str) -> dict | None: ...
    def set(self, key: str, value: dict) -> None: ...
    def delete(self, key: str) -> None: ...


# (method, url, params, form, bearer token) -> decoded JSON body
Http = Callable[[str, str, dict | None, dict | None, str | None], dict]


def http_json(
    method: str,
    url: str,
    params: dict | None = None,
    form: dict | None = None,
    token: str | None = None,
) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        # Google's error bodies name the problem (invalid_grant, ...) and hold no secrets.
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise GoogleAuthError(f"Google returned HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise GoogleAuthError(f"Could not reach Google: {exc.reason}") from None
    return json.loads(body) if body else {}


class GoogleOAuth:
    """One Google grant for one provider ("gmail" or "calendar")."""

    def __init__(
        self,
        provider: str,
        scopes: list[str],
        store: TokenStore,
        http: Http = http_json,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        self.provider = provider
        self.scopes = scopes
        self.store = store
        self.http = http
        self.client_id = client_id or os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.redirect_uri = redirect_uri or os.getenv("OAUTH_REDIRECT_URI", "")
        self._refresh_lock = threading.Lock()

    @property
    def _token_key(self) -> str:
        return f"{self.provider}:tokens"

    @property
    def _state_key(self) -> str:
        return f"{self.provider}:state"

    def start_auth(self) -> str:
        if not (self.client_id and self.client_secret and self.redirect_uri):
            raise GoogleAuthError(
                "GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and OAUTH_REDIRECT_URI must be set"
            )
        # The provider prefix lets one /oauth/callback route pick the right connector.
        state = f"{self.provider}.{secrets.token_urlsafe(24)}"
        self.store.set(self._state_key, {"state": state})
        query = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            # offline + consent is what makes Google return a refresh token
            "access_type": "offline",
            "prompt": "consent",
            # No include_granted_scopes: each provider keeps its own grant, so revoking
            # Gmail cannot take Calendar down with it and neither token carries both scopes.
        }
        return f"{AUTH_URL}?{urllib.parse.urlencode(query)}"

    def finish_auth(self, params: dict) -> dict:
        """Check the callback, swap the code for tokens, store them. Returns the tokens."""
        if params.get("error"):
            raise GoogleAuthError(f"Google sign-in was not completed: {params['error']}")
        expected = (self.store.get(self._state_key) or {}).get("state", "")
        # Compared as bytes: compare_digest raises on non-ASCII str, and state is caller-supplied.
        received = str(params.get("state", "")).encode()
        if not expected or not secrets.compare_digest(expected.encode(), received):
            raise GoogleAuthError("OAuth state did not match; start the connection again")
        self.store.delete(self._state_key)
        if not params.get("code"):
            raise GoogleAuthError("Google did not return an authorization code")

        reply = self.http(
            "POST",
            TOKEN_URL,
            None,
            {
                "code": params["code"],
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            },
            None,
        )
        tokens = self._tokens_from(reply, previous=None)
        self.store.set(self._token_key, tokens)
        return tokens

    def granted_scopes(self) -> list[str]:
        tokens = self.store.get(self._token_key) or {}
        return str(tokens.get("scope", "")).split()

    def is_connected(self) -> bool:
        return self.store.get(self._token_key) is not None

    def access_token(self) -> str:
        # The lock makes parallel fetch workers share one refresh instead of racing.
        with self._refresh_lock:
            tokens = self.store.get(self._token_key)
            if not tokens:
                raise GoogleAuthError(f"{self.provider} is not connected")
            if tokens["expires_at"] - EXPIRY_MARGIN_S > time.time():
                return tokens["access_token"]
            if not tokens.get("refresh_token"):
                raise GoogleAuthError(f"{self.provider} access expired; reconnect it")
            reply = self.http(
                "POST",
                TOKEN_URL,
                None,
                {
                    "refresh_token": tokens["refresh_token"],
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                },
                None,
            )
            tokens = self._tokens_from(reply, previous=tokens)
            self.store.set(self._token_key, tokens)
            return tokens["access_token"]

    def get(self, url: str, params: dict | None = None) -> dict:
        """Authorized GET against a Google API."""
        return self.http("GET", url, params, None, self.access_token())

    def revoke(self) -> None:
        tokens = self.store.get(self._token_key)
        if not tokens:
            return
        try:
            token = tokens.get("refresh_token") or tokens["access_token"]
            self.http("POST", REVOKE_URL, None, {"token": token}, None)
        except GoogleAuthError:
            pass  # already revoked or expired on Google's side; still drop our copy
        finally:
            self.store.delete(self._token_key)

    @staticmethod
    def _tokens_from(reply: dict, previous: dict | None) -> dict:
        if "access_token" not in reply:
            raise GoogleAuthError("Google did not return an access token")
        previous = previous or {}
        return {
            "access_token": reply["access_token"],
            # A refresh reply omits the refresh token; keep the one we have.
            "refresh_token": reply.get("refresh_token") or previous.get("refresh_token"),
            "expires_at": time.time() + int(reply.get("expires_in", 3600)),
            "scope": reply.get("scope") or previous.get("scope", ""),
        }
