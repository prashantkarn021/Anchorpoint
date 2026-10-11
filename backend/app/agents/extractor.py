"""Extractor agent: one relevant item -> CandidateRecord.

No tools: the model only fills CandidateRecord. `enforce` re-checks it in code. The trusted
profile and triage hint sit outside the fence; only source text is fenced as untrusted.
"""

import io
import re

from pypdf import PdfReader
from strands import Agent

from backend.app.agents.llm import CallBudget, make_model, model_slot
from backend.app.agents.prompts import EXTRACTOR_SYSTEM, item_text, wrap_document
from backend.app.common.hashing import content_hash
from backend.app.models import CandidateRecord, Profile, RawItem, RecordType

REVIEW_THRESHOLD = 0.7  # plan §7: confidence below this sets Record.needs_review
UNVERIFIED_QUOTE_CAP = 0.5
MIN_QUOTE_CHARS = 8  # "$" or "Maya" is in every doc; too short to count as evidence

# ponytail: in-process dict; persist to disk if demo reset restarts the server
_cache: dict[tuple[str, str, str], CandidateRecord] = {}


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


def enforce(c: CandidateRecord, text: str) -> CandidateRecord:
    """Code-side guardrail: rules own `factor`; confidence in [0, 1]; the quote must really be in the source."""
    update: dict = {"factor": None, "confidence": min(max(c.confidence, 0.0), 1.0)}
    # the model sometimes writes newlines as a literal backslash-n; read those as whitespace
    quote = " ".join(c.evidence_quote.replace("\\n", " ").split()) if c.evidence_quote else None
    update["evidence_quote"] = quote
    if quote and (len(quote) < MIN_QUOTE_CHARS or _norm(quote) not in _norm(text)):
        update["evidence_quote"] = None
        update["confidence"] = min(update["confidence"], UNVERIFIED_QUOTE_CAP)
    return c.model_copy(update=update)


_ADDR_WORDS = {
    "street": "st", "avenue": "ave", "av": "ave", "road": "rd", "drive": "dr", "boulevard": "blvd",
    "lane": "ln", "court": "ct", "place": "pl", "terrace": "ter", "parkway": "pkwy", "highway": "hwy",
    "apartment": "unit", "apt": "unit", "suite": "unit", "ste": "unit",
}  # no N/North folding: "E St" and "East St" can be different streets


def address_key(s: str) -> str:
    """Comparable form: lowercase, no punctuation, St/Street and Apt/#/Unit folded together."""
    out: list[str] = []
    for t in re.findall(r"[^\W_]+", s.lower().replace("#", " unit ")):
        t = _ADDR_WORDS.get(t, t)
        if not (t == "unit" and out and out[-1] == "unit"):  # "Apt #4B" -> one unit token
            out.append(t)
    return " ".join(out)


def match_home(c: CandidateRecord, home_address: str) -> CandidateRecord:
    """R2 compares the home address exactly; if the doc names the same place, use the profile's spelling."""
    # ponytail: whole-address match only; a doc that omits city/ZIP or spells out the state stays as written
    if c.address and (key := address_key(c.address)) and key == address_key(home_address):
        return c.model_copy(update={"address": home_address})
    return c


def needs_review(c: CandidateRecord) -> bool:
    """For P2's Record mapper (CandidateRecord has no needs_review field)."""
    return c.confidence < REVIEW_THRESHOLD


def pdf_text(data: bytes) -> str:
    """Text layer of a PDF for Attachment.text_extracted; '' for scans (vision path later)."""
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages).strip()


def _run_agent(prompt: str, budget: CallBudget | None = None) -> CandidateRecord:
    agent = Agent(model=make_model(budget), system_prompt=EXTRACTOR_SYSTEM, tools=[], callback_handler=None)
    with model_slot:
        result = agent(prompt, structured_output_model=CandidateRecord, limits={"turns": 3})
    if result.structured_output is None:
        raise RuntimeError(f"extractor gave no valid output (stop_reason={result.stop_reason})")
    return result.structured_output


def _holder(profile: Profile) -> str:
    return f"Account holder (trusted, from the app): {profile.name}, home address: {profile.home_address}"


def _key(item: RawItem, profile: Profile, doc_type: RecordType) -> tuple[str, str, str]:
    # profile edit -> new key -> re-extract
    return content_hash(item_text(item)), doc_type, content_hash(_holder(profile))


def extract(item: RawItem, profile: Profile, doc_type: RecordType,
            budget: CallBudget | None = None, *, use_cache: bool = True) -> tuple[CandidateRecord, bool]:
    """Returns (record, cached). A cache hit makes no model request, so it costs no budget.
    Raises on model failure or an exhausted budget; pipeline.ingest turns that into an event."""
    text, holder, key = item_text(item), _holder(profile), _key(item, profile, doc_type)
    if use_cache and key in _cache:
        return _cache[key].model_copy(deep=True), True  # callers can't mutate the cache
    prompt = f"{holder}\nTriage guessed doc_type: {doc_type}\n\n" + wrap_document(text)
    record = enforce(_run_agent(prompt, budget), text)
    record = match_home(record, profile.home_address)
    if use_cache:
        _cache[key] = record
    return record.model_copy(deep=True), False
