"""Auditor agent: explains the rules' findings in plain language; never decides anything.

Rules own findings, scores and the verdict. The model only writes {narrative, questions_for_cpa}.
No tools. Findings go in the untrusted fence (their `detail` can carry text copied from emails).
`check` rejects invented record or rule IDs; on any failure we fall back to a template, flagged
ai_explanation_available=False so the UI can say so.
"""

import json
import logging
import re
import unicodedata

from pydantic import BaseModel
from strands import Agent

from backend.app.agents.llm import make_model
from backend.app.agents.prompts import AUDITOR_SYSTEM, wrap_document
from backend.app.models import Assessment, Finding

log = logging.getLogger(__name__)

MAX_QUESTIONS = 5


class AuditorResult(BaseModel):  # P1-internal; P2 copies these into RiskReport
    narrative: str
    questions_for_cpa: list[str]
    ai_explanation_available: bool


class _AuditorOut(BaseModel):
    narrative: str
    questions_for_cpa: list[str]


def _allowed_ids(findings: list[Finding], assessment: Assessment | None) -> set[str]:
    ids = {i for f in findings for i in f.record_ids}
    if assessment:
        ids |= {i for fs in assessment.factors for i in fs.record_ids}
    return ids


def check(out: _AuditorOut, findings: list[Finding], assessment: Assessment | None) -> bool:
    """True only if the text cites real record IDs and mentions only the rules we gave it."""
    # NFKC folds lookalikes (full-width brackets, digits) before any matching
    text = unicodedata.normalize("NFKC", " ".join([out.narrative, *out.questions_for_cpa]))
    allowed = _allowed_ids(findings, assessment)
    # "[a]" and grouped "[a, b]" both count; every ID inside must be real
    cited = {i.strip() for group in re.findall(r"\[([^\[\]]+)\]", text) for i in group.split(",")}
    # Bare/parenthesised IDs too (rent-9999, Rent-99): a word-dash-digit token whose prefix starts a
    # real ID must itself be real. Prose like "mid-2026", "W-2", "covid-19" has no ID prefix, so passes.
    # ponytail: an invented bare ID with a brand-new prefix ("xyz-1") or no digit isn't caught
    lower_allowed = {i.lower() for i in allowed}
    prefixes = {i.split("-")[0] for i in lower_allowed}
    bare = {t.lower() for t in re.findall(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)*-\d[a-z0-9-]*\b", text, re.IGNORECASE)}
    bare = {t for t in bare if t.split("-")[0] in prefixes}
    # ponytail: "Rules 1 and 9" only reads the first number; a fake R9 is caught when written as one
    rules = {int(n) for n in re.findall(r"\bR(?:ules?)?[\s#-]{0,2}(\d+)", text, re.IGNORECASE)}
    return (bool(out.narrative.strip())
            and 1 <= len(out.questions_for_cpa) <= MAX_QUESTIONS
            and cited <= allowed and bare <= lower_allowed
            and rules <= {int(f.rule_id[1:]) for f in findings if f.rule_id[1:].isdigit()})


def template(findings: list[Finding], assessment: Assessment | None) -> AuditorResult:
    """Deterministic fallback: same facts, no model."""
    head = f"Your tax-home evidence is {assessment.status.replace('_', ' ')} ({assessment.score}/100). " \
        if assessment else ""
    if not findings:
        return AuditorResult(narrative=head + "No issues were found in your records.",
                             questions_for_cpa=["Is there anything else I should keep for my tax-home records?"],
                             ai_explanation_available=False)
    parts = [f"{f.title} ({f.severity})" + (" " + " ".join(f"[{i}]" for i in f.record_ids) if f.record_ids else "")
             for f in findings]
    return AuditorResult(
        narrative=head + f"{len(findings)} finding(s): " + "; ".join(parts) + ".",
        questions_for_cpa=[f"How should I handle \"{f.title}\" ({f.rule_id})?" for f in findings][:MAX_QUESTIONS],
        ai_explanation_available=False,
    )


def _payload(findings: list[Finding], assessment: Assessment | None) -> str:
    data = {"findings": [f.model_dump() for f in findings]}
    if assessment:
        data["assessment"] = assessment.model_dump(include={"score", "status", "factors_met", "factors"})
    return json.dumps(data, separators=(",", ":"))  # compact: stays far under the fence's char cap


def _run_agent(prompt: str) -> _AuditorOut:
    agent = Agent(model=make_model(), system_prompt=AUDITOR_SYSTEM, tools=[], callback_handler=None)
    result = agent(prompt, structured_output_model=_AuditorOut, limits={"turns": 3})
    if result.structured_output is None:
        raise RuntimeError(f"auditor gave no valid output (stop_reason={result.stop_reason})")
    return result.structured_output


def explain(findings: list[Finding], assessment: Assessment | None = None) -> AuditorResult:
    """Never raises: model off, timeout or a failed check -> templated explanation."""
    try:
        out = _run_agent(wrap_document(_payload(findings, assessment)))
    except Exception as e:  # noqa: BLE001 - any model failure means "use the template"
        log.warning("auditor model failed (%s); using template", type(e).__name__)
        return template(findings, assessment)
    if not check(out, findings, assessment):
        log.warning("auditor output cited unknown record or rule IDs; using template")
        return template(findings, assessment)
    return AuditorResult(**out.model_dump(), ai_explanation_available=True)
