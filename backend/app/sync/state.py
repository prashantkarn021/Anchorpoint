"""What each sync has already done: the provider cursor and which items are finished."""

import sqlite3
from contextlib import contextmanager


class SyncState:
    """Lives in the same SQLite file as the ledger and the vault, in its own tables."""

    def __init__(self, path: str):
        self.path = path
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS sync_cursor (
                    provider TEXT PRIMARY KEY,
                    cursor TEXT,
                    last_sync TEXT,
                    note TEXT
                );
                CREATE TABLE IF NOT EXISTS sync_seen (
                    provider TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    PRIMARY KEY (provider, source_id)
                );
            """)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA journal_mode = WAL")
            with connection:
                yield connection
        finally:
            connection.close()

    def _row(self, provider: str):
        with self._connection() as connection:
            return connection.execute(
                "SELECT cursor, last_sync, note FROM sync_cursor WHERE provider = ?", (provider,)
            ).fetchone()

    def _set(self, provider: str, column: str, value: str | None) -> None:
        with self._connection() as connection:
            connection.execute("INSERT OR IGNORE INTO sync_cursor (provider) VALUES (?)", (provider,))
            connection.execute(f"UPDATE sync_cursor SET {column} = ? WHERE provider = ?", (value, provider))

    def cursor(self, provider: str) -> str | None:
        row = self._row(provider)
        return row[0] if row else None

    def set_cursor(self, provider: str, cursor: str) -> None:
        self._set(provider, "cursor", cursor)

    def last_sync(self, provider: str) -> str | None:
        row = self._row(provider)
        return row[1] if row else None

    def set_last_sync(self, provider: str, when: str) -> None:
        self._set(provider, "last_sync", when)

    def note_changed(self, provider: str, note: str | None) -> bool:
        """Remember the latest status note; True when it differs from the previous one.

        Lets a repeating problem (model down, budget used up) reach the feed once, not every poll.
        """
        row = self._row(provider)
        if row and row[2] == note:
            return False
        self._set(provider, "note", note)
        return True

    def seen(self, provider: str) -> dict[str, str]:
        """source_id -> outcome for every item that needs no more work."""
        with self._connection() as connection:
            return dict(connection.execute(
                "SELECT source_id, outcome FROM sync_seen WHERE provider = ?", (provider,)
            ).fetchall())

    def mark(self, provider: str, source_id: str, outcome: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO sync_seen (provider, source_id, outcome) VALUES (?, ?, ?) "
                "ON CONFLICT(provider, source_id) DO UPDATE SET outcome = excluded.outcome",
                (provider, source_id, outcome),
            )

    def clear(self) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM sync_cursor")
            connection.execute("DELETE FROM sync_seen")
