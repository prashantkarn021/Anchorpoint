import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.connectors.google_oauth import GoogleAuthError
from backend.app.main import app
from backend.app.routers import demo
from backend.app.routers.demo import inbox_address, inject_writer


class FakeWriter:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.inserted = []

    def insert(self, email, to_name, to_address) -> str:
        if self.fail:
            raise GoogleAuthError("Gmail returned HTTP 403: insufficient scope")
        self.inserted.append((email, to_name, to_address))
        return f"msg-{len(self.inserted)}"


@pytest.fixture
def client():
    def use(writer):
        app.dependency_overrides[inject_writer] = lambda: writer
        app.dependency_overrides[inbox_address] = lambda: "maya@example.com"
        return TestClient(app)

    yield use
    app.dependency_overrides.clear()


def test_inject_inserts_a_fresh_utility_bill_for_the_demo_persona(client):
    writer = FakeWriter()

    response = client(writer).post("/api/demo/inject")

    assert response.status_code == 200
    body = response.json()
    assert body["inserted"] == 1
    assert body["emails"][0]["source_id"] == "msg-1"
    assert body["emails"][0]["from"] == "Evergreen Power & Light"
    email, to_name, to_address = writer.inserted[0]
    assert (to_name, to_address) == ("Maya Torres", "maya@example.com")
    assert "1842 Fictional Lantern Lane" in email.body


def test_inject_reports_a_gmail_failure_without_details(client):
    response = client(FakeWriter(fail=True)).post("/api/demo/inject")

    assert response.status_code == 502
    assert "scope" not in response.json()["detail"]


def test_inject_is_unavailable_until_the_injector_is_granted(monkeypatch, tmp_path):
    monkeypatch.setenv("SEED_GOOGLE_CLIENT_ID", "seed-client")
    monkeypatch.setenv("SEED_GOOGLE_CLIENT_SECRET", "seed-secret")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'demo.db'}")
    monkeypatch.setenv("TOKEN_ENC_KEY", Fernet.generate_key().decode())
    demo.default_vault.cache_clear()

    with pytest.raises(HTTPException) as raised:
        inject_writer()

    demo.default_vault.cache_clear()
    assert raised.value.status_code == 503
    assert "not been granted" in raised.value.detail


def test_inject_is_unavailable_without_the_seeder_client(monkeypatch):
    monkeypatch.delenv("SEED_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("SEED_GOOGLE_CLIENT_SECRET", raising=False)

    with pytest.raises(HTTPException) as raised:
        inject_writer()

    assert raised.value.status_code == 503
    assert "SEED_GOOGLE_CLIENT_ID" in raised.value.detail
