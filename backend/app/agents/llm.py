import os
import threading
from typing import Any

import openai
from dotenv import load_dotenv
from strands.models.openai import OpenAIModel

load_dotenv()  # local dev; in docker the env comes from compose

MAX_CONCURRENT_CALLS = 4
# Held around every agent call (triage, extractor, auditor), whatever threads the caller uses.
# ponytail: per-process; one API process in the demo
model_slot = threading.BoundedSemaphore(MAX_CONCURRENT_CALLS)

REQUEST_RETRIES = 1  # our own retry, so it is counted; the OpenAI SDK's hidden retries are off
MAX_REQUESTS_PER_SYNC = 40


class BudgetExhausted(Exception):
    """Raised before a model request when the sync's request budget is used up."""


class CallBudget:
    """Model *requests* allowed in one sync: every structured-output turn and every retry costs 1.
    Thread-safe; create one per sync."""

    def __init__(self, max_requests: int = MAX_REQUESTS_PER_SYNC):
        self.left = max_requests
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.left <= 0:
                return False
            self.left -= 1
            return True


class AkamaiModel(OpenAIModel):
    """Akamai rejects `tools: []` (Strands sends it for tool-less agents), so drop it when empty.

    stream() runs once per model request (each agent turn, each Strands throttle retry), so the
    budget is charged there, before anything is sent.
    """

    def __init__(self, *args: Any, budget: CallBudget | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._budget = budget

    def format_request(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        request = super().format_request(*args, **kwargs)
        if not request.get("tools"):
            request.pop("tools", None)
        return request

    async def stream(self, *args: Any, **kwargs: Any):
        for attempt in range(1 + REQUEST_RETRIES):
            if self._budget is not None and not self._budget.take():
                raise BudgetExhausted("model request budget used up for this sync")
            started = False
            inner = super().stream(*args, **kwargs)
            try:
                async for event in inner:
                    started = True
                    yield event
                return
            except (openai.APIConnectionError, openai.InternalServerError):  # incl. timeouts
                if started or attempt == REQUEST_RETRIES:
                    raise
            finally:
                await inner.aclose()  # close the per-request OpenAI client now, even on early exit


def make_model(budget: CallBudget | None = None) -> OpenAIModel:
    """Strands model pointed at Akamai's OpenAI-compatible inference. Shared by all P1 agents."""
    return AkamaiModel(
        client_args={
            "api_key": os.environ["INFERENCE_API_KEY"],
            "base_url": os.environ["INFERENCE_BASE_URL"],
            "timeout": 30,
            "max_retries": 0,  # retries happen in AkamaiModel.stream, where the budget sees them
        },
        model_id=os.environ["MODEL_ID"],
        budget=budget,
    )


def budget_exhausted(e: BaseException) -> bool:
    """True if BudgetExhausted is anywhere in the chain (Strands wraps it in EventLoopException)."""
    seen: set[int] = set()
    while e is not None and id(e) not in seen:
        if isinstance(e, BudgetExhausted):
            return True
        seen.add(id(e))
        e = e.__cause__ or e.__context__
    return False
