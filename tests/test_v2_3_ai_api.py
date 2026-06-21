from __future__ import annotations

from fastapi.testclient import TestClient

from app.ai_brain.local_ai_worker import LocalAIWorker
from app.ai_brain.service import HybridAIBrainService
from app.api.ai_routes import create_ai_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app


def _client(postgres_test_schema) -> TestClient:
    run_migrations()
    app = create_app()
    return TestClient(app)


def test_ai_health_costs_cache_escalations_and_decisions_work(postgres_test_schema) -> None:
    client = _client(postgres_test_schema)
    assert client.get("/ai/health").status_code == 200
    assert client.get("/ai/costs").status_code == 200
    assert client.get("/ai/cache").status_code == 200
    assert client.get("/ai/escalations").status_code == 200
    assert client.get("/ai/decisions").status_code == 200


def test_ai_analyze_requires_reason_and_returns_structured_result(postgres_test_schema) -> None:
    run_migrations()
    service = HybridAIBrainService(
        connection_factory=DatabaseConnectionFactory(),
        local_worker=LocalAIWorker(transport=lambda *_args: {"summary": "classified", "confidence": 0.8, "risk_flags": []}),
    )
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(create_ai_router(connection_factory=DatabaseConnectionFactory(), ai_service=service))
    client = TestClient(app)
    missing_reason = client.post("/ai/analyze", json={"task_type": "MARKET_CLASSIFICATION", "input_payload": {"text": "BTC"}})
    assert missing_reason.status_code == 422
    response = client.post(
        "/ai/analyze",
        json={"task_type": "MARKET_CLASSIFICATION", "input_payload": {"text": "BTC"}, "allow_cloud": False, "reason": "test"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["structured_output"]["summary"] in {"classified", "AI analysis blocked by safety policy"}
    assert "order_intent" not in str(payload).lower()


def test_cloud_disabled_by_default(postgres_test_schema) -> None:
    client = _client(postgres_test_schema)
    assert client.get("/ai/health").json()["cloud_enabled"] is False
