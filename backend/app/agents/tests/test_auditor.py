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


def test_unknown_prefix_id_falls_back_in_narrative_and_questions(monkeypatch):
    # PR #13 review: an invented ID with a prefix no real record uses
    assert not _ai(monkeypatch, "Your rent is supported by fabricated-999, so R1 is resolved.")
    assert not _ai(monkeypatch, "June rent is missing [rent-05].", questions=["Does fabricated-999 count?"])
    assert not _ai(monkeypatch, "Rent proof [rent-2026] is on file.")  # real prefix, year-shaped: still checked
    for text in ["See fabricated-2026.", "See lease-renewal-2026.",          # year-shaped invented IDs
                 "R–12 applies.", "Rule—12 applies.", "R‑12 too",  # en/em dash, non-breaking hyphen
                 "Proof: rent‑9999.", "R­12 applies.", "Proof: rent\u200b-9999.",  # invisible chars
                 "R\u034f12 applies.", "R\ufe0f12 applies.", "Proof: rent-\u034f9999.", "R\u316412 applies.",
                 "Missing proof\nR9 applies.", "\u200b\u200b"]:  # newline keeps words apart; invisible-only = empty
        assert not _ai(monkeypatch, text), text


def test_invented_rule_falls_back_in_any_form(monkeypatch):
    for text in ["R1 and also R9 high risk.", "Rule 9 applies.", "see r9", "R 9 too", "Rules 9 and 1", "R-9 applies", "Rule #9"]:
        assert not _ai(monkeypatch, text), text
    assert _ai(monkeypatch, "Rule 1 and R3 apply.")


def test_every_rule_in_a_group_is_checked(monkeypatch):
    # PR #13 review: grouped mentions used to read only the first number
    for text in ["Rules 1 and 9 apply to your missing housing evidence [rent-05].",
                 "R1, R3 and R9 apply.", "Rules 1, 3 & 9", "Rule 1/9",
                 "Rules 1-9 apply.", "Rules 1 to 9.", "Rules 1 through 9 apply."]:
        assert not _ai(monkeypatch, text), text
    assert not _ai(monkeypatch, "June rent is missing [rent-05].", questions=["Do Rules 3 and 9 apply?"])
    for text in ["Rules 1 and 3 apply [rent-05].", "R1 in 2026 [rent-05].", "R1 for 10 months [rent-05].",
                 "R-1 applies [rent-05].", "Rule-1 applies.", "Rules 1-3 apply.",
                 "Your H-1B, W-2s and i-94 since mid-June-2026, post-9/11 rules aside [rent-05]."]:
        assert _ai(monkeypatch, text), text


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
