from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.api.routes import create_router


class _FakeAIService:
    def benchmark_json(self, *, run_model_tests: bool = True) -> dict[str, object]:
        return {
            "status": "PARTIAL",
            "provider_reachable": True,
            "models": ["qwen3:4b"],
            "tests": [{"model": "qwen3:4b", "task": "tiny_json", "valid_json": True, "schema_valid": True}],
            "recommended_fast_json_model": None,
            "recommended_reasoning_model": "qwen3:4b",
            "recommended_ai_mode": "FAST_ONLY_DEGRADED",
            "recommended_pull_command": "ollama pull llama3.2:1b",
        }


def test_benchmark_json_endpoint_exposes_reliability(monkeypatch) -> None:
    monkeypatch.setattr(routes, "AIMarketIntelligenceMeshOrgan", lambda: _FakeAIService())
    app = FastAPI()
    app.include_router(create_router())

    response = TestClient(app).post("/dashboard/api/v2/control/ai-mesh-intelligence/benchmark-json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_ai_mode"] == "FAST_ONLY_DEGRADED"
    assert payload["recommended_pull_command"] == "ollama pull llama3.2:1b"
