"""Fill the demo account's Google Calendar from a persona spec.

Uses the same *seeder* OAuth client (Desktop app type) as seed_gmail.py, never the app's web
client. Sign in as the demo account. Tokens stay in memory for the run. The grant is not
revoked: that would also revoke the server's grants (see the note in main).
From the repo root:

    docker compose run --rm -p 127.0.0.1:8765:8765 -e PYTHONPATH=/srv \
        -v ./scripts:/srv/scripts -v /path/to/seeder_client.json:/secrets/seeder.json:ro \
        api python scripts/seed_calendar.py --client /secrets/seeder.json --clear

Add --dry-run to list the events without signing in. --clear removes only events this seeder
wrote before (they carry a private tag); nothing else in the calendar is touched.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for seed_gmail's sign-in helper
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, team convention

from seed_gmail import sign_in

from backend.app.connectors.google_oauth import GoogleAuthError
from backend.app.seed.calendar_writer import SCOPES, CalendarWriter, events
from backend.app.seed.persona import Persona


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--persona", default="maya")
    parser.add_argument("--client", help="seeder OAuth client JSON (Desktop app)")
    parser.add_argument("--clear", action="store_true", help="delete previously seeded events first")
    parser.add_argument("--dry-run", action="store_true", help="list the events only")
    args = parser.parse_args()

    seed = events(Persona.load(args.persona))
    for event in seed:
        span = f" to {event.end}" if event.end != event.start else ""
        print(f"  {event.start}{span:<14}  {event.title}")
    print(f"{len(seed)} events")
    if args.dry_run:
        return
    if not args.client:
        sys.exit("--client is required unless --dry-run is given")

    try:
        writer = CalendarWriter(sign_in(args.client, SCOPES))
        if args.clear:
            print(f"deleted {writer.clear()} previously seeded event(s)", flush=True)
        print(f"inserted {len(writer.insert_all(seed))} events", flush=True)
        # Deliberately no revoke. Google keeps one grant per user per Cloud project, shared by
        # every OAuth client in it, so revoking the seeder's token also revokes the server's
        # Gmail, Calendar and inject grants. The token is in memory only and dies with this run.
    except GoogleAuthError as exc:
        sys.exit(f"SEED FAILED: {exc}")
    print("SEED DONE")


if __name__ == "__main__":
    main()
