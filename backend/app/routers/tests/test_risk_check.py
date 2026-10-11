import pytest
from fastapi.testclient import TestClient

from backend.app.agents.auditor import AuditorResult
from backend.app.models import Finding
from backend.app.routers import risk
from backend.app.routers.risk import verdict


def _f(severity: str) -> Finding:
    return Finding(rule_id="R1", severity=severity, title="t", detail="d", recommended_action="a")


def test_verdict_comes_from_rule_severities():
    assert verdict([]) == "go"
    assert verdict([_f("info")]) == "go"
    assert verdict([_f("info"), _f("warn")]) == "review_with_cpa"
    assert verdict([_f("warn"), _f("high")]) == "high_risk"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend.app.ledger import Ledger
    from backend.app.main import app
    from backend.app.routers.records import get_ledger

    calls = []

    def fake_explain(findings, assessment=None):  # no model in unit tests
        calls.append(findings)
        return AuditorResult(narrative="explained", questions_for_cpa=["q?"], ai_explanation_available=True)

    monkeypatch.setattr(risk, "explain", fake_explain)
    ledger = Ledger(str(tmp_path / "risk.db"))
    app.dependency_overrides[get_ledger] = lambda: ledger
    try:
        with TestClient(app) as c:
            c.explain_calls = calls
            yield c
    finally:
        app.dependency_overrides.clear()


def test_offered_assignment_gets_a_rule_verdict_and_explanation(client):
    r = client.post("/api/risk-check", json={"assignment_id": "a5"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == verdict([Finding(**f) for f in body["findings"]])  # rules decide
    assert body["narrative"] == "explained" and body["ai_explanation_available"] is True
    assert client.explain_calls and len(client.explain_calls[0]) == len(body["findings"])
    assert {f["rule_id"] for f in body["findings"]} >= {"R5"}  # offer extends the Denver streak


def test_unknown_assignment_and_unmatched_offer_text(client):
    assert client.post("/api/risk-check", json={"assignment_id": "nope"}).status_code == 404
    assert client.post("/api/risk-check", json={"assignment_id": "a4"}).status_code == 404  # active, not offered
    assert client.post("/api/risk-check", json={"offer_text": "a job somewhere"}).status_code == 422
    assert client.post("/api/risk-check", json={"offer_text": "x" * 5000}).status_code == 422


def test_offer_text_matching_an_offered_assignment(client):
    r = client.post("/api/risk-check", json={"offer_text": "Extension offer: 17 more weeks in Denver"})
    assert r.status_code == 200 and r.json()["verdict"] in ("go", "review_with_cpa", "high_risk")
