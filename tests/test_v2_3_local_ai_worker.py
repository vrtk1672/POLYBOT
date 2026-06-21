from __future__ import annotations

from app.ai_brain.local_ai_worker import LocalAIWorker


def test_mocked_local_response_parsed() -> None:
    worker = LocalAIWorker(transport=lambda *_args: {"summary": "ok", "confidence": 0.8, "risk_flags": ["none"]})
    result = worker.generate_json(model_name="qwen3:8b", prompt="json", input_payload={"text": "hello"})
    assert result.status == "COMPLETED"
    assert result.output["summary"] == "ok"
    assert result.confidence == 0.8


def test_unavailable_invalid_json_and_timeout_handled_safely() -> None:
    assert LocalAIWorker().generate_json(model_name="qwen3:8b", prompt="", input_payload={}).status == "UNAVAILABLE"
    invalid = LocalAIWorker(transport=lambda *_args: "not json").generate_json(model_name="qwen3:8b", prompt="", input_payload={})
    assert invalid.status == "FAILED"

    def timeout(*_args):
        raise TimeoutError()

    timed_out = LocalAIWorker(transport=timeout).generate_json(model_name="qwen3:8b", prompt="", input_payload={})
    assert timed_out.status == "TIMEOUT"


def test_no_secrets_logged_in_output() -> None:
    worker = LocalAIWorker(transport=lambda *_args: {"api_key": "secret", "summary": "ok"})
    result = worker.generate_json(model_name="qwen3:8b", prompt="api_key secret", input_payload={"private_key": "secret"})
    assert result.output["api_key"] == "<redacted>"
    assert result.raw_output_redacted is not None
