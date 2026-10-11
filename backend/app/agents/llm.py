import os
from typing import Any

from dotenv import load_dotenv
from strands.models.openai import OpenAIModel

load_dotenv()  # local dev; in docker the env comes from compose


class AkamaiModel(OpenAIModel):
    """Akamai rejects `tools: []` (Strands sends it for tool-less agents), so drop it when empty."""

    def format_request(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        request = super().format_request(*args, **kwargs)
        if not request.get("tools"):
            request.pop("tools", None)
        return request


def make_model() -> OpenAIModel:
    """Strands model pointed at Akamai's OpenAI-compatible inference. Shared by all P1 agents."""
    return AkamaiModel(
        client_args={
            "api_key": os.environ["INFERENCE_API_KEY"],
            "base_url": os.environ["INFERENCE_BASE_URL"],
            "timeout": 30,
            "max_retries": 1,
        },
        model_id=os.environ["MODEL_ID"],
    )
