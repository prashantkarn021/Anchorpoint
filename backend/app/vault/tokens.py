"""Encrypted token store on SQLite. Implements the connectors' TokenStore protocol."""

import json
import os
import sqlite3
from contextlib import contextmanager
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


class VaultError(Exception):
    """The vault is misconfigured or a stored value cannot be decrypted."""


class TokenVault:
    """Values are Fernet-encrypted before they touch disk; only keys are stored in the clear."""

    def __init__(self, path: str, key: str):
        if not key:
            raise VaultError("TOKEN_ENC_KEY is not set")
        try:
            self._fernet = Fernet(key)
        except ValueError:
            raise VaultError("TOKEN_ENC_KEY is not a valid Fernet key") from None
        self.path = path
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS vault_tokens (key TEXT PRIMARY KEY, value BLOB NOT NULL)"
            )

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

    def get(self, key: str) -> dict | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM vault_tokens WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(self._fernet.decrypt(row[0]))
        except InvalidToken:
            raise VaultError(f"stored value for {key!r} was encrypted with a different key") from None

    def set(self, key: str, value: dict) -> None:
        encrypted = self._fernet.encrypt(json.dumps(value).encode())
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO vault_tokens (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, encrypted),
            )

    def delete(self, key: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM vault_tokens WHERE key = ?", (key,))


def database_path() -> str:
    """File path out of DATABASE_URL (sqlite:////data/anchorpoint.db -> /data/anchorpoint.db)."""
    url = os.getenv("DATABASE_URL", "sqlite:///anchorpoint.db")
    return url.removeprefix("sqlite:///")


@lru_cache
def default_vault() -> TokenVault:
    return TokenVault(database_path(), os.getenv("TOKEN_ENC_KEY", ""))
