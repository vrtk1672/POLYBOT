from __future__ import annotations

import pytest

from app.services.ai_mesh_intelligence import AIMarketIntelligenceMeshOrgan, AIMeshConfig


class _FastAI:
    def status(self) -> dict[str, object]:
        return {
            "available": True,
            "provider": "OLLAMA",
            "models": ["qwen3:4b"],
            "fast_model": "qwen3:4b",
            "reasoning_model": "qwen3:4b",
        }

    def complete_json(self, **kwargs) -> dict[str, object]:
        return {"status": "OK", "summary": "ok", "confidence": 0.5, "_model_provider": "OLLAMA", "_model_name": kwargs.get("model")}


class _TimeoutAI(_FastAI):
    def complete_json(self, **kwargs) -> dict[str, object]:
        raise TimeoutError("timed out")


def test_diagnostics_reports_model_status() -> None:
    service = AIMarketIntelligenceMeshOrgan(local_ai=_FastAI(), config=AIMeshConfig())

    diagnostics = service.diagnostics()

    assert diagnostics["provider_reachable"] is True
    assert diagnostics["ai_mode"] in {"ENABLED", "FAST_ONLY", "DEGRADED"}


def test_benchmark_handles_reachable_model() -> None:
    service = AIMarketIntelligenceMeshOrgan(local_ai=_FastAI(), config=AIMeshConfig(fast_timeout_seconds=1, reasoning_timeout_seconds=1))

    result = service.benchmark(run_model_tests=True)

    assert result["status"] == "OK"
    assert all(item["success"] for item in result["tests"])


def test_benchmark_handles_timeout_safely() -> None:
    service = AIMarketIntelligenceMeshOrgan(local_ai=_TimeoutAI(), config=AIMeshConfig(fast_timeout_seconds=1, reasoning_timeout_seconds=1))

    result = service.benchmark(run_model_tests=True)

    assert result["status"] == "PARTIAL"
    assert result["latest_error"]
