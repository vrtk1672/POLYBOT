from __future__ import annotations

import pytest

from app.ai_brain.contracts import AICaseFile, AIDecision, AIModelTier, AIRequest, AIResponse, AITaskType
from app.events.types import EventType


def test_required_task_types_and_model_tiers_exist() -> None:
    for task in [
        "MARKET_CLASSIFICATION",
        "RULES_SUMMARY",
        "MARKET_LINKING",
        "NEWS_DEDUP",
        "CONTEXT_SUMMARY",
        "CASE_FILE_BUILD",
        "WORDING_RISK_PRECHECK",
        "CONTRADICTION_CHECK",
        "TRAP_PRECHECK",
        "POST_TRADE_REVIEW_PREP",
    ]:
        assert AITaskType(task)
    assert AIModelTier.LOCAL_FAST.value == "LOCAL_FAST"
    assert AIModelTier.CLOUD_ESCALATION.value == "CLOUD_ESCALATION"


def test_ai_request_response_and_case_file_validate() -> None:
    request = AIRequest(task_type=AITaskType.RULES_SUMMARY, input_payload={"text": "rules"})
    response = AIResponse(task_type=request.task_type, model_name="qwen3:14b", structured_output={"summary": "ok"})
    case_file = AICaseFile(market_id="m1", question="Will this work?", allowed_for_ai=True)
    assert request.correlation_id
    assert response.structured_output["summary"] == "ok"
    assert case_file.market_id == "m1"


def test_ai_decision_has_no_trade_execution_fields() -> None:
    AIDecision(decision_type="INTERPRETATION", task_type=AITaskType.RULES_SUMMARY, output_json={"summary": "ok"})
    with pytest.raises(ValueError):
        AIDecision(
            decision_type="BAD",
            task_type=AITaskType.RULES_SUMMARY,
            output_json={"order_intent_id": "forbidden"},
        )


def test_ai_event_types_exist() -> None:
    for event_type in [
        "ai.request.created",
        "ai.cache.hit",
        "ai.budget.blocked",
        "ai.local.completed",
        "ai.cloud.escalated",
        "ai.cloud.completed",
        "ai.decision.logged",
        "ai.cost.recorded",
        "ai.model.performance.updated",
    ]:
        assert EventType(event_type)
