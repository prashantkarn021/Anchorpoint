"""Triage agent: is this item evidence, what type, and is it an injection attempt?

No tools: the model only fills TriageResult. `enforce` re-applies the safety rules in code,
so a fooled model can't route a suspicious item onward. Triage reads the same text the
extractor will (body + attachments, same cap), so an injection can't hide past a snippet.
"""

from pydantic import BaseModel, Field
from strands import Agent

from backend.app.agents.llm import CallBudget, make_model, model_slot
from backend.app.agents.prompts import TRIAGE_SYSTEM, item_text, wrap_document
from backend.app.common.hashing import content_hash
from backend.app.models import RawItem, RecordType

# ponytail: in-process dict like the extractor's; persist to disk if demo reset restarts the server
_cache: dict[str, "TriageResult"] = {}


class TriageResult(BaseModel):  # P1-internal (agreed with P2), not in models.py
    relevant: bool
    doc_type: RecordType | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    suspicious: bool = False


def enforce(r: TriageResult) -> TriageResult:
    """Code-side guardrail: suspicious is never relevant; relevant needs a type; irrelevant has none."""
    if r.suspicious or not r.relevant or r.doc_type is None:
        return r.model_copy(update={"relevant": False, "doc_type": None})
    return r


def triage(item: RawItem, budget: CallBudget | None = None, *, use_cache: bool = True) -> TriageResult:
    """A cache hit makes no model request, so it costs no budget (plan §7: cache by content hash).
    Raises on model failure or an exhausted budget; pipeline.ingest turns that into an event."""
    text = item_text(item)
    key = content_hash(text)  # same text the model sees, so same answer
    if use_cache and key in _cache:
        return _cache[key].model_copy()  # callers can't mutate the cache
    agent = Agent(model=make_model(budget), system_prompt=TRIAGE_SYSTEM, tools=[], callback_handler=None)
    with model_slot:
        result = agent(
            wrap_document(text),
            structured_output_model=TriageResult,
            limits={"turns": 3},  # invalid output gets retried by Strands; cap it
        )
    if result.structured_output is None:
        raise RuntimeError(f"triage gave no valid output (stop_reason={result.stop_reason})")
    checked = enforce(result.structured_output)
    if use_cache:
        _cache[key] = checked  # only successful results are cached
    return checked.model_copy()
