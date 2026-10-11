import re

from backend.app.agents import auditor
from backend.app.agents.auditor import _AuditorOut, explain, template
from backend.app.models import Assessment, FactorStatus, Finding

FINDINGS = [
    Finding(rule_id="R1", severity="warn", title="Missing housing payment evidence",
            detail="Housing payment proof is missing for: 2026-06.", record_ids=["rent-05", "rent-07"],
            recommended_action="Find the June rent receipt or bank transaction."),
    Finding(rule_id="R3", severity="warn", title="Missing return-trip evidence",
            detail="Proof of a trip home is missing for: Tucson -> Denver.", record_ids=[],
            recommended_action="Find proof of a trip home or ask your CPA."),
]
ASSESSMENT = Assessment(score=67, status="needs_attention", factors_met=2, findings=FINDINGS, factors=[
    FactorStatus(factor=2, label="Home housing expenses", score=34, met=True, record_ids=["lease-1"]),
])


def _model(monkeypatch, out=None, exc=None):
    def fake(prompt):
        if exc:
            raise exc
        return out
    monkeypatch.setattr(auditor, "_run_agent", fake)


def test_valid_output_passes(monkeypatch):
    _model(monkeypatch, _AuditorOut(narrative="June rent is missing (R1) [rent-05]; lease on file [lease-1].",
                                    questions_for_cpa=["Is one missing month a problem?"]))
    r = explain(FINDINGS, ASSESSMENT)
    assert r.ai_explanation_available and "[lease-1]" in r.narrative


Q = ["Is one missing month a problem?"]


def _ai(monkeypatch, narrative, questions=Q) -> bool:
    _model(monkeypatch, _AuditorOut(narrative=narrative, questions_for_cpa=questions))
    return explain(FINDINGS, ASSESSMENT).ai_explanation_available


def test_grouped_cites_are_checked_one_by_one(monkeypatch):
    assert _ai(monkeypatch, "Rent on file [rent-05, rent-07].")
    assert not _ai(monkeypatch, "Rent on file [rent-05, rent-99].")


def test_invented_record_id_falls_back_in_any_form(monkeypatch):
    for text in ["All good [rent-99].", "All good (rent-99).", "All good rent-99.", "All good ［rent-99］.",
                 "Rent-99 is on file."]:
        assert not _ai(monkeypatch, text), text
    for text in ["Your W-2 job and the 2026-06 gap [rent-05].", "By mid-2026 [rent-05].", "Post covid-19 rent-05."]:
        assert _ai(monkeypatch, text), text  # prose, not IDs


def test_invented_rule_falls_back_in_any_form(monkeypatch):
    for text in ["R1 and also R9 high risk.", "Rule 9 applies.", "see r9", "R 9 too", "Rules 9 and 1", "R-9 applies", "Rule #9"]:
        assert not _ai(monkeypatch, text), text
    assert _ai(monkeypatch, "Rule 1 and R3 apply.")


def test_question_count_enforced(monkeypatch):
    assert not _ai(monkeypatch, "June rent is missing [rent-05].", questions=[])
    assert not _ai(monkeypatch, "June rent is missing [rent-05].", questions=Q * 6)


def test_model_off_falls_back(monkeypatch):
    _model(monkeypatch, exc=ConnectionError("inference down"))
    r = explain(FINDINGS, ASSESSMENT)
    assert r.ai_explanation_available is False and "67/100" in r.narrative
    assert len(r.questions_for_cpa) == len(FINDINGS)


def test_template_cites_only_real_ids():
    r = template(FINDINGS, ASSESSMENT)
    assert set(re.findall(r"\[([^\]]+)\]", r.narrative)) == {"rent-05", "rent-07"}


def test_template_without_findings():
    r = template([], None)
    assert "No issues" in r.narrative and r.questions_for_cpa and not r.ai_explanation_available
