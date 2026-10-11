import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from backend.app.vault.tokens import TokenVault, VaultError, database_path

TOKENS = {"access_token": "ya29.secret-access", "refresh_token": "1//secret-refresh", "expires_at": 1.5}


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "vault.db")


def test_round_trip_and_overwrite(path):
    vault = TokenVault(path, Fernet.generate_key().decode())

    vault.set("gmail:tokens", TOKENS)
    vault.set("gmail:tokens", {**TOKENS, "access_token": "ya29.newer"})

    assert vault.get("gmail:tokens")["access_token"] == "ya29.newer"
    assert vault.get("missing") is None


def test_values_are_encrypted_at_rest(path):
    TokenVault(path, Fernet.generate_key().decode()).set("gmail:tokens", TOKENS)

    stored = sqlite3.connect(path).execute("SELECT key, value FROM vault_tokens").fetchall()
    raw = Path(path).read_bytes()

    assert [key for key, _ in stored] == ["gmail:tokens"]
    assert b"secret-access" not in raw
    assert b"secret-refresh" not in raw


def test_survives_reopening_with_the_same_key(path):
    key = Fernet.generate_key().decode()
    TokenVault(path, key).set("gmail:tokens", TOKENS)

    assert TokenVault(path, key).get("gmail:tokens") == TOKENS


def test_wrong_key_cannot_read(path):
    TokenVault(path, Fernet.generate_key().decode()).set("gmail:tokens", TOKENS)

    with pytest.raises(VaultError, match="different key"):
        TokenVault(path, Fernet.generate_key().decode()).get("gmail:tokens")


def test_delete(path):
    vault = TokenVault(path, Fernet.generate_key().decode())
    vault.set("gmail:state", {"state": "gmail.abc"})

    vault.delete("gmail:state")
    vault.delete("gmail:state")

    assert vault.get("gmail:state") is None


@pytest.mark.parametrize("key", ["", "not-a-fernet-key"])
def test_refuses_to_start_without_a_valid_key(path, key):
    with pytest.raises(VaultError, match="TOKEN_ENC_KEY"):
        TokenVault(path, key)


def test_database_path_comes_from_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////data/anchorpoint.db")

    assert database_path() == "/data/anchorpoint.db"
