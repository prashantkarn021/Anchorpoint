"""SQLite records with an append-only audit trail."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime

from backend.app.models import AuditEvent, Record

EDITABLE_FIELDS = {
    "amount", "payee", "address", "date", "period_start", "period_end", "type", "factor",
}


class Ledger:
    def __init__(self, path: str):
        self.path = path
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    factor INTEGER,
                    user_status TEXT NOT NULL,
                    json TEXT NOT NULL,
                    UNIQUE(provider, source_id)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    record_id TEXT,
                    detail TEXT NOT NULL
                );
            """)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA journal_mode = WAL")
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _append_event(connection, event: AuditEvent):
        connection.execute(
            "INSERT INTO audit_events (ts, actor, action, record_id, detail) VALUES (?, ?, ?, ?, ?)",
            (event.ts.astimezone(UTC).isoformat(), event.actor, event.action, event.record_id, event.detail),
        )

    @staticmethod
    def _read_record(connection, row) -> Record:
        record = Record.model_validate_json(row["json"])
        record.history = [
            AuditEvent.model_validate(dict(event))
            for event in connection.execute(
                "SELECT * FROM audit_events WHERE record_id = ? ORDER BY ts, id", (record.id,),
            )
        ]
        return record

    @staticmethod
    def _write_record(connection, record: Record, *, created: bool):
        fields = (
            record.source.provider, record.source.source_id, record.type, record.factor,
            record.user_status, record.model_dump_json(exclude={"history"}), record.id,
        )
        if created:
            connection.execute(
                "INSERT INTO records (provider, source_id, type, factor, user_status, json, id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", fields,
            )
        else:
            connection.execute(
                "UPDATE records SET provider = ?, source_id = ?, type = ?, factor = ?, "
                "user_status = ?, json = ? WHERE id = ?", fields,
            )

    def upsert_record(self, record: Record) -> tuple[Record, bool]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM records WHERE provider = ? AND source_id = ?",
                (record.source.provider, record.source.source_id),
            ).fetchone()
            created = row is None
            previous_values = {}
            if row is not None:
                existing = self._read_record(connection, row)
                if existing.source.content_hash == record.source.content_hash:
                    return existing, False
                old_fields = existing.model_dump(mode="json")
                new_fields = record.model_dump(mode="json")
                previous_values = {
                    field: old_fields[field] for field in sorted(EDITABLE_FIELDS)
                    if old_fields[field] != new_fields[field]
                }
                record = record.model_copy(update={
                    "id": existing.id, "user_status": existing.user_status,
                })
            self._write_record(connection, record, created=created)
            self._append_event(connection, AuditEvent(
                ts=datetime.now(UTC), actor="agent" if record.extracted_by == "agent" else "system",
                action="extracted" if created else "edited", record_id=record.id,
                detail="Record extracted from source." if created else (
                    "Source content changed on re-sync. "
                    + json.dumps({"previous_values": previous_values}, separators=(",", ":"))
                ),
            ))
            row = connection.execute("SELECT * FROM records WHERE id = ?", (record.id,)).fetchone()
            return self._read_record(connection, row), created

    def get_record(self, id: str) -> Record | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM records WHERE id = ?", (id,)).fetchone()
            return self._read_record(connection, row) if row is not None else None

    def list_records(self, *, type=None, factor=None, status=None, provider=None) -> list[Record]:
        filters = {"type": type, "factor": factor, "user_status": status, "provider": provider}
        selected = {key: value for key, value in filters.items() if value is not None}
        where = " WHERE " + " AND ".join(f"{key} = ?" for key in selected) if selected else ""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM records" + where + " ORDER BY json_extract(json, '$.date') DESC, id",
                tuple(selected.values()),
            ).fetchall()
            return [self._read_record(connection, row) for row in rows]

    def update_record(self, id: str, user_status=None, edits=None) -> Record:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM records WHERE id = ?", (id,)).fetchone()
            if row is None:
                raise KeyError(id)
            edits = edits or {}
            if set(edits) - EDITABLE_FIELDS:
                raise ValueError("Edits contain protected fields")
            if user_status is not None and user_status not in ("confirmed", "rejected", "pending"):
                raise ValueError("User status must be confirmed, rejected or pending")
            values = self._read_record(connection, row).model_dump(exclude={"history"})
            edits = {key: value for key, value in edits.items() if values[key] != value}
            if user_status == values["user_status"]:
                user_status = None
            values.update(edits)
            if user_status is not None:
                values["user_status"] = user_status
            record = Record.model_validate(values)
            if edits or user_status is not None:
                self._write_record(connection, record, created=False)
            for action, detail in (
                ("edited" if user_status == "pending" else user_status, "User changed record status."),
                ("edited" if edits else None, "User edited fields: " + ", ".join(sorted(edits))),
            ):
                if action is not None:
                    self._append_event(connection, AuditEvent(
                        ts=datetime.now(UTC), actor="user", action=action, record_id=id, detail=detail,
                    ))
            row = connection.execute("SELECT * FROM records WHERE id = ?", (id,)).fetchone()
            return self._read_record(connection, row)

    def clear(self, provider: str | None = None) -> tuple[int, int]:
        """Delete records and audit events; returns how many of each. For reset and revoke.

        With a provider, only that provider's records and their events go. Only this ledger's
        tables are touched: the token vault and sync state share the file and are kept.
        """
        with self._connection() as connection:
            if provider is None:
                records = connection.execute("DELETE FROM records").rowcount
                events = connection.execute("DELETE FROM audit_events").rowcount
                return records, events
            events = connection.execute(
                "DELETE FROM audit_events WHERE record_id IN (SELECT id FROM records WHERE provider = ?)",
                (provider,),
            ).rowcount
            records = connection.execute("DELETE FROM records WHERE provider = ?", (provider,)).rowcount
            return records, events

    def add_event(self, event: AuditEvent) -> None:
        if event.record_id is not None:
            raise ValueError("add_event requires an event without a record_id")
        with self._connection() as connection:
            self._append_event(connection, event)

    def list_events(self, limit: int = 100, after_id: int | None = None) -> list[dict]:
        if limit < 0:
            raise ValueError("limit must be nonnegative")
        where = " WHERE id > ?" if after_id is not None else ""
        params = (after_id, limit) if after_id is not None else (limit,)
        order = "ASC" if after_id is not None else "DESC"
        with self._connection() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM audit_events" + where + f" ORDER BY id {order} LIMIT ?", params,
            )]
