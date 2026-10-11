"""Gate G2 check: real Google consent on localhost, then read the demo inbox.

Tokens stay in memory, are never printed, and the grant is revoked at the end.
Stop the api container first (it owns port 8000), then run:

    docker compose run --rm -p 127.0.0.1:8000:8000 -v ./scripts:/srv/scripts \
        -e PYTHONPATH=/srv api python scripts/p4_g2_check.py
"""

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl, urlparse

from backend.app.connectors.gmail import GmailConnector
from backend.app.connectors.google_oauth import GoogleAuthError

WAIT_SECONDS = 600


class MemoryStore:
    def __init__(self) -> None:
        self.data: dict = {}

    def get(self, key: str) -> dict | None:
        return self.data.get(key)

    def set(self, key: str, value: dict) -> None:
        self.data[key] = value

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


def wait_for_callback() -> dict:
    received: dict = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path != "/api/oauth/callback":
                self.send_error(404)
                return
            received.update(parse_qsl(url.query))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Anchorpoint received the sign-in. You can close this tab.")
            done.set()

        def log_message(self, *args) -> None:  # the query string holds the auth code
            pass

    server = HTTPServer(("0.0.0.0", 8000), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    finished = done.wait(WAIT_SECONDS)
    server.shutdown()
    if not finished:
        sys.exit("G2 RED: no sign-in arrived within 10 minutes")
    return received


def main() -> None:
    # An empty query reads any recent mail; the real prefilter needs the seeded inbox.
    connector = GmailConnector(MemoryStore(), query="")
    print("Open this link in the browser where the demo account is signed in:\n", flush=True)
    print(connector.start_auth(), flush=True)
    print("\nWaiting for the sign-in...", flush=True)
    try:
        connection = connector.finish_auth(wait_for_callback())
        print(f"consent ok, scopes: {connection.scopes}", flush=True)
        items, cursor = connector.fetch_since(None)
        print(f"fetched {len(items)} message(s), cursor {cursor}")
        for item in items[:3]:
            print(f"  {item.received_at:%Y-%m-%d}  {item.meta['from']}  |  {item.meta['subject']}")
        connector.revoke()
        print("grant revoked")
    except GoogleAuthError as exc:
        sys.exit(f"G2 RED: {exc}")
    print("G2 (localhost) GREEN" if items else "G2 RED: consent worked but the inbox is empty")


if __name__ == "__main__":
    main()
