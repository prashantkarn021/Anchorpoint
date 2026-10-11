from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.agents.llm import CallBudget
from backend.app.connectors import upload


def test_vision_uses_image_content_schema_and_no_write_tools(monkeypatch):
    calls = {}
    class Agent:
        def __init__(self, **kwargs):
            calls["config"] = kwargs

        def __call__(self, content, **kwargs):
            calls["content"] = content
            calls["args"] = kwargs
            return SimpleNamespace(structured_output=upload.Transcription(text="Synthetic receipt $10"))
    budget = CallBudget()
    monkeypatch.setenv("VISION_MODEL_ID", "synthetic-vision-model")
    monkeypatch.setattr(upload, "make_model", lambda actual_budget, **kwargs: (actual_budget, kwargs))
    monkeypatch.setattr(upload, "Agent", Agent)
    assert upload.transcribe(b"synthetic image bytes", budget) == "Synthetic receipt $10"
    assert calls["config"]["tools"] == []
    assert calls["config"]["model"] == (budget, {"model_id": "synthetic-vision-model"})
    assert "untrusted" in calls["config"]["system_prompt"]
    assert calls["content"][1]["image"]["source"]["bytes"] == b"synthetic image bytes"
    assert calls["args"]["structured_output_model"] is upload.Transcription


def test_transcription_rejects_extra_fields_and_excessive_text():
    with pytest.raises(ValidationError):
        upload.Transcription(text="receipt", findings=["invented"])
    with pytest.raises(ValidationError):
        upload.Transcription(text="x" * (upload.MAX_DOC_CHARS + 1))
