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

from backend.app.agents.llm import make_model, model_slot
from backend.app.agents.prompts import AUDITOR_SYSTEM, wrap_document
from backend.app.models import Assessment, Finding

log = logging.getLogger(__name__)

MAX_QUESTIONS = 5

# A rule mention plus any grouped numbers after it: "R1", "Rule #9", "Rules 1 and 9", "R1, R3 & 9",
# and ranges "Rules 1-9" / "1 to 9" / "1 through 9" (both ends are checked).
# Only 1-3 digit numbers continue a group, so "R1 in 2026" doesn't read 2026 as a rule.
# ponytail: "R1 and 12 months" reads 12 as a rule -> safe false fallback to the template
_RULE_GROUP = re.compile(
    r"\bR(?:ules?)?[\s#-]{0,2}\d{1,3}\b"
    r"(?:\s*(?:,|&|/|-|\band\b|\bor\b|\bto\b|\bthrough\b)\s*(?:R(?:ules?)?[\s#-]{0,2})?\d{1,3}\b)*",
    re.IGNORECASE,
)
# Record IDs carry a digit after a dash (rent-09, trip-home-1). Any such token must be a real ID.
_ID_LIKE = re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)*-\d[a-z0-9-]*\b", re.IGNORECASE)
# Prose that looks ID-shaped but isn't a record: tax/visa forms, "covid-19", "post-9/11",
# "mid-2026" / "mid-june-2026" years, and dashed rule mentions ("R-1", which _RULE_GROUP checks).
# ponytail: a short list; an unlisted form falls back to the template (safe, just less AI text)
_PROSE_TOKENS = {"w-2", "w-2s", "w-4", "w-9", "i-9", "i-94", "k-1", "k-1s", "h-1b", "covid-19", "post-9"}
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?" \
    r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
# only "early/mid/late[-month]-YYYY" or "month-YYYY": an invented "fabricated-2026" is still caught
_PROSE_FORM = re.compile(rf"(?:(?:early|mid|late)(?:-{_MONTH})?|{_MONTH})-(?:19|20)\d{{2}}|r(?:ules?)?-\d{{1,3}}")
_DASHES = re.compile(r"[‐-―−﹘﹣]")  # hyphen/en/em/minus lookalikes
_INVISIBLE_CATS = {"Cf", "Mn", "Me"}  # dropped; controls ("Cc", incl. newlines) become spaces instead
_FILLERS = {"ᅟ", "ᅠ", "ㅤ", "ﾠ"}  # Hangul fillers: letters that render as nothing


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


def _visible(s: str) -> str:
    """Checking copy of model text (never shown). NFKC folds lookalikes (full-width brackets, digits).
    Invisible chars are dropped so "R\\u00ad12" (renders "R12") can't dodge the checks: format chars
    (soft hyphen, zero-width), combining marks/variation selectors, Hangul fillers, controls. NFKC
    leaves Unicode dashes alone, so they map to "-" or "R–12" / "rent‑9999" would dodge every check.
    ponytail: cross-script lookalikes (Cyrillic "Р12") aren't folded."""
    s = unicodedata.normalize("NFKC", s)
    s = "".join(" " if unicodedata.category(c) == "Cc" else c for c in s
                if unicodedata.category(c) not in _INVISIBLE_CATS and c not in _FILLERS)
    return _DASHES.sub("-", s)


def check(out: _AuditorOut, findings: list[Finding], assessment: Assessment | None) -> bool:
    """True only if the text cites real record IDs and mentions only the rules we gave it."""
    text = _visible(" ".join([out.narrative, *out.questions_for_cpa]))
    allowed = _allowed_ids(findings, assessment)
    # "[a]" and grouped "[a, b]" both count; every ID inside must be real
    cited = {i.strip() for group in re.findall(r"\[([^\[\]]+)\]", text) for i in group.split(",")}
    # Bare/parenthesised references too, whatever the prefix (rent-9999, Rent-99, fabricated-999).
    # Only known prose shapes are exempt, and never when the prefix belongs to a real ID ("rent-2026").
    lower_allowed = {i.lower() for i in allowed}
    prefixes = {i.split("-")[0] for i in lower_allowed}
    bare = {t.lower() for t in _ID_LIKE.findall(text)} - lower_allowed
    invented = {t for t in bare
                if t.split("-")[0] in prefixes or not (t in _PROSE_TOKENS or _PROSE_FORM.fullmatch(t))}
    # ponytail: assumes record IDs carry a digit (all fixture/ledger IDs do); a digit-free bare ID isn't seen
    rules = {int(n) for group in _RULE_GROUP.findall(text) for n in re.findall(r"\d+", group)}
    return (bool(_visible(out.narrative).strip())  # a narrative of only zero-width chars is empty
            and 1 <= len(out.questions_for_cpa) <= MAX_QUESTIONS
            and cited <= allowed and not invented
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
    with model_slot:
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
