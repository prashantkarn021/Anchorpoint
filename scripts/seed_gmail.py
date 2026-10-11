"""Fill the demo Gmail inbox from a persona spec.

Needs the *seeder* OAuth client (Desktop app type), never the app's web client.
Tokens stay in memory for the run. From the repo root:

    docker compose run --rm -p 127.0.0.1:8765:8765 -e PYTHONPATH=/srv \
        -v ./scripts:/srv/scripts -v /path/to/seeder_client.json:/secrets/seeder.json:ro \
        api python scripts/seed_gmail.py --client /secrets/seeder.json --clear

Add --dry-run to see what would be sent without signing in or touching the inbox.
"""

import argparse
import json
import sys
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl, urlparse

from backend.app.connectors.google_oauth import GoogleAuthError, GoogleOAuth
from backend.app.seed.emails import generate
from backend.app.seed.gmail_writer import SCOPES, GmailWriter
from backend.app.seed.persona import Persona

# What POST /api/demo/inject needs: add a message, nothing else.
INSERT_SCOPES = ["https://www.googleapis.com/auth/gmail.insert"]

PORT = 8765
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
            query = dict(parse_qsl(urlparse(self.path).query))
            if "code" not in query and "error" not in query:
                self.send_error(404)
                return
            received.update(query)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Seeder signed in. You can close this tab.")
            done.set()

        def log_message(self, *args) -> None:  # the query string holds the auth code
            pass

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    finished = done.wait(WAIT_SECONDS)
    server.shutdown()
    if not finished:
        sys.exit("No sign-in arrived within 10 minutes")
    return received


def sign_in(client_file: str, scopes: list[str] = SCOPES) -> GoogleOAuth:
    with open(client_file, encoding="utf-8") as handle:
        client = json.load(handle)
    if "installed" not in client:
        sys.exit("That is not a Desktop-app OAuth client. Do not seed with the app's web client.")
    oauth = GoogleOAuth(
        "seed",
        scopes,
        MemoryStore(),
        client_id=client["installed"]["client_id"],
        client_secret=client["installed"]["client_secret"],
        redirect_uri=f"http://localhost:{PORT}",
    )
    print("Open this link in the browser where the demo account is signed in:\n", flush=True)
    print(oauth.start_auth(), flush=True)
    print("\nWaiting for the sign-in...", flush=True)
    oauth.finish_auth(wait_for_callback())
    return oauth


def summarize(emails) -> None:
    by_kind = Counter(email.kind for email in emails)
    by_record = Counter(email.record for email in emails if email.record)
    size = sum(len(data) for email in emails for _, _, data in email.attachments)
    print(f"{len(emails)} emails, {emails[0].sent_at:%Y-%m-%d} to {emails[-1].sent_at:%Y-%m-%d}")
    print("  by kind:   " + ", ".join(f"{kind} {count}" for kind, count in sorted(by_kind.items())))
    print("  by record: " + ", ".join(f"{kind} {count}" for kind, count in sorted(by_record.items())))
    print(f"  attachments: {sum(len(email.attachments) for email in emails)} PDFs, {size // 1024} KB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--persona", default="maya")
    parser.add_argument("--client", help="seeder OAuth client JSON (Desktop app)")
    parser.add_argument("--clear", action="store_true", help="trash everything in the inbox first")
    parser.add_argument("--dry-run", action="store_true", help="generate and summarize only")
    parser.add_argument(
        "--grant-inject",
        metavar="FILE",
        help="sign in with the insert-only scope and write the token to FILE, to be loaded "
        "into the server vault as seed:tokens; seeds nothing",
    )
    args = parser.parse_args()

    if args.grant_inject:
        if not args.client:
            sys.exit("--client is required with --grant-inject")
        try:
            oauth = sign_in(args.client, INSERT_SCOPES)
        except GoogleAuthError as exc:
            sys.exit(f"GRANT FAILED: {exc}")
        with open(args.grant_inject, "w", encoding="utf-8") as handle:
            json.dump(oauth.store.get("seed:tokens"), handle)
        print("insert-only token written; load it into the vault, then delete the file")
        return

    persona = Persona.load(args.persona)
    emails = generate(persona)
    summarize(emails)
    if args.dry_run:
        return
    if not args.client:
        sys.exit("--client is required unless --dry-run is given")

    try:
        writer = GmailWriter(sign_in(args.client))
        address = writer.address()
        print(f"signed in as {address}", flush=True)
        if args.clear:
            print(f"moved {writer.clear()} existing message(s) to the trash", flush=True)
        ids = writer.insert_all(emails, persona.profile["name"], address)
        print(f"inserted {len(ids)} emails")
        # Deliberately no revoke. Google keeps one grant per user per Cloud project, shared by
        # every OAuth client in it, so revoking the seeder's token also revokes the server's
        # Gmail, Calendar and inject grants. The token is in memory only and dies with this run.
    except GoogleAuthError as exc:
        sys.exit(f"SEED FAILED: {exc}")
    print("SEED DONE")


if __name__ == "__main__":
    main()
