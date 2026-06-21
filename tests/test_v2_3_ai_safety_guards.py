from __future__ import annotations

from app.ai_brain.contracts import AIRequest, AITaskType
from app.ai_brain.local_ai_worker import LocalAIWorker
from app.ai_brain.service import HybridAIBrainService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.runtime.state_governor import StateGovernor


def test_ai_cannot_create_order_intent_and_data_only_has_no_trading_side_effects(postgres_test_schema) -> None:
    run_migrations()
    service = HybridAIBrainService(
        connection_factory=DatabaseConnectionFactory(),
        local_worker=LocalAIWorker(transport=lambda *_args: {"summary": "ok", "confidence": 0.8, "risk_flags": []}),
    )
    response = service.analyze(AIRequest(task_type=AITaskType.MARKET_CLASSIFICATION, input_payload={"text": "BTC"}), reason="test")
    with DatabaseConnectionFactory().connect() as conn:
        order_events = conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type IN ('order.intent.created','order.created')").fetchone()
    assert response.structured_output
    assert order_events["count"] == 0


def test_kill_blocks_new_ai_analysis(postgres_test_schema) -> None:
    run_migrations()
    StateGovernor().activate_kill(actor="test", reason="ai safety test")
    service = HybridAIBrainService(
        connection_factory=DatabaseConnectionFactory(),
        local_worker=LocalAIWorker(transport=lambda *_args: {"summary": "should not run", "confidence": 0.9}),
    )
    response = service.analyze(AIRequest(task_type=AITaskType.MARKET_CLASSIFICATION, input_payload={"text": "BTC"}), reason="test")
    assert response.structured_output["status"] == "BLOCKED"
    assert response.structured_output["blocked_reason"] == "runtime_mode_blocks_ai"


def test_low_completeness_returns_uncertainty_and_env_alone_cannot_enable_cloud(monkeypatch) -> None:
    monkeypatch.setenv("AI_CLOUD_ENABLED", "true")
    service = HybridAIBrainService(local_worker=LocalAIWorker(transport=lambda *_args: {"summary": "ok", "confidence": 0.8}))
    response = service.analyze(
        AIRequest(task_type=AITaskType.TRAP_PRECHECK, market_id="missing", input_payload={"text": "BTC"}),
        allow_cloud=True,
        reason="test",
    )
    assert response.recommended_action == "NO_TRADE"
    assert "blocked" in response.structured_output["status"].lower()


def test_no_secrets_in_api_like_response() -> None:
    service = HybridAIBrainService(local_worker=LocalAIWorker(transport=lambda *_args: {"api_key": "secret", "summary": "ok", "confidence": 0.8}))
    response = service.analyze(AIRequest(task_type=AITaskType.MARKET_CLASSIFICATION, input_payload={"api_key": "secret"}), reason="test")
    assert "secret" not in str(response.model_dump(mode="json")).lower()
