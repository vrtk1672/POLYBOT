from __future__ import annotations

from app.services.ai_mesh_intelligence import AIMarketIntelligenceMeshOrgan, AIMeshConfig


class _MostlyJsonAI:
    def status(self) -> dict[str, object]:
        return {
            "available": True,
            "provider": "OLLAMA",
            "models": ["qwen3:4b", "tiny-json:latest"],
            "fast_json_model": "tiny-json:latest",
            "fast_model": "tiny-json:latest",
            "reasoning_model": "qwen3:4b",
        }

    def complete_json(self, **kwargs) -> dict[str, object]:
        model = kwargs.get("model")
        if model == "qwen3:4b" and "thesis" in str(kwargs.get("prompt")).lower():
            raise ValueError("AI_INVALID_JSON: Unterminated string")
        return {
            "status": "OK",
            "summary": "json ok",
            "entities": [],
            "topics": [],
            "direction_hint": "UNKNOWN",
            "thesis_type": "UNKNOWN",
            "confidence": 0.4,
            "_model_provider": "OLLAMA",
            "_model_name": model,
        }


def test_benchmark_json_returns_model_diagnostics() -> None:
    service = AIMarketIntelligenceMeshOrgan(
        local_ai=_MostlyJsonAI(),
        config=AIMeshConfig(fast_timeout_seconds=1, reasoning_timeout_seconds=1),
    )

    result = service.benchmark_json(run_model_tests=True)

    assert result["models"] == ["qwen3:4b", "tiny-json:latest"]
    assert result["tests"]
    assert result["recommended_ai_mode"] in {"FAST_JSON_ONLY", "ENABLED", "FAST_ONLY_DEGRADED"}
    assert any(item["task"] == "thesis_skeleton" for item in result["tests"])


def test_qwen_can_be_classified_partial_when_invalid_json_persists() -> None:
    service = AIMarketIntelligenceMeshOrgan(
        local_ai=_MostlyJsonAI(),
        config=AIMeshConfig(fast_timeout_seconds=1, reasoning_timeout_seconds=1),
    )

    result = service.benchmark_json(run_model_tests=True)
    qwen_failures = [item for item in result["tests"] if item["model"] == "qwen3:4b" and item["fallback_used"]]

    assert qwen_failures
    assert result["status"] in {"PARTIAL", "OK"}
