import pytest
from fastapi.testclient import TestClient

from backend.app.connectors.google_oauth import GoogleAuthError
from backend.app.main import app
from backend.app.routers.oauth import gmail_connector


class FakeConnector:
    def __init__(self, fail: str | None = None):
        self.fail = fail
        self.finished_with = None

    def start_auth(self) -> str:
        if self.fail:
            raise GoogleAuthError(self.fail)
        return "https://accounts.google.com/o/oauth2/v2/auth?state=gmail.abc"

    def finish_auth(self, params: dict):
        if self.fail:
            raise GoogleAuthError(self.fail)
        self.finished_with = params


@pytest.fixture
def connect(monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)

    def use(connector):
        app.dependency_overrides[gmail_connector] = lambda: connector
        return TestClient(app, follow_redirects=False)

    yield use
    app.dependency_overrides.clear()


def test_start_returns_the_google_redirect_url(connect):
    response = connect(FakeConnector()).post("/api/connections/gmail/start")

    assert response.status_code == 200
    assert response.json()["redirect_url"].startswith("https://accounts.google.com/")


def test_start_reports_missing_configuration(connect):
    response = connect(FakeConnector(fail="GOOGLE_CLIENT_ID must be set")).post(
        "/api/connections/gmail/start"
    )

    assert response.status_code == 503
    assert "GOOGLE_CLIENT_ID" in response.json()["detail"]


def test_callback_finishes_auth_and_returns_to_connections(connect):
    connector = FakeConnector()

    response = connect(connector).get("/api/oauth/callback?code=abc&state=gmail.xyz")

    assert response.status_code == 303
    assert response.headers["location"] == "/connections?connected=gmail"
    assert connector.finished_with == {"code": "abc", "state": "gmail.xyz"}


def test_callback_uses_frontend_url_when_set(connect, monkeypatch):
    client = connect(FakeConnector())
    monkeypatch.setenv("FRONTEND_URL", "http://localhost/")

    response = client.get("/api/oauth/callback?code=abc&state=gmail.xyz")

    assert response.headers["location"] == "http://localhost/connections?connected=gmail"


def test_callback_passes_on_a_denied_consent(connect):
    connector = FakeConnector()

    response = connect(connector).get("/api/oauth/callback?error=access_denied&state=gmail.xyz")

    assert response.headers["location"] == "/connections?error=access_denied"
    assert connector.finished_with is None


def test_callback_sanitizes_the_error_code(connect):
    response = connect(FakeConnector()).get(
        "/api/oauth/callback?error=%3Cscript%3Ealert(1)%3C/script%3E"
    )

    assert response.headers["location"] == "/connections?error=scriptalertscript"


def test_callback_rejects_another_providers_state(connect):
    connector = FakeConnector()

    response = connect(connector).get("/api/oauth/callback?code=abc&state=calendar.xyz")

    assert response.headers["location"] == "/connections?error=unknown_provider"
    assert connector.finished_with is None


def test_callback_hides_failure_details_from_the_url(connect):
    response = connect(FakeConnector(fail="OAuth state did not match")).get(
        "/api/oauth/callback?code=abc&state=gmail.forged"
    )

    assert response.headers["location"] == "/connections?error=connection_failed"
