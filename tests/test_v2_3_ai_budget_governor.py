from __future__ import annotations

from app.ai_brain.budget_governor import AIBudgetGovernor
from app.ai_brain.contracts import AICaseFile, AITaskType


def test_cache_hit_blocks_model_call() -> None:
    decision = AIBudgetGovernor().evaluate(task_type=AITaskType.RULES_SUMMARY, cache_hit=True)
    assert decision.allowed is False
    assert decision.blocked_reason == "cache_hit"


def test_low_completeness_blocks_cloud_and_too_low_blocks_all() -> None:
    governor = AIBudgetGovernor()
    low_cloud = governor.evaluate(
        task_type=AITaskType.TRAP_PRECHECK,
        case_file=AICaseFile(data_completeness_score=60),
        cloud_requested=True,
    )
    too_low = governor.evaluate(task_type=AITaskType.RULES_SUMMARY, case_file=AICaseFile(data_completeness_score=20))
    assert low_cloud.allowed is True
    assert low_cloud.cloud_allowed is False
    assert low_cloud.blocked_reason == "cloud_blocked_low_data_completeness"
    assert too_low.allowed is False


def test_closed_and_stale_market_blocks_ai() -> None:
    governor = AIBudgetGovernor()
    closed = governor.evaluate(task_type=AITaskType.RULES_SUMMARY, case_file=AICaseFile(data_completeness_score=90, metadata={"closed": True}))
    stale = governor.evaluate(task_type=AITaskType.RULES_SUMMARY, case_file=AICaseFile(data_completeness_score=90, stale_fields=["market_snapshot"]))
    assert closed.blocked_reason == "market_closed"
    assert stale.blocked_reason == "stale_data"


def test_low_value_task_can_be_blocked_if_configured() -> None:
    decision = AIBudgetGovernor(block_low_value_tasks=True).evaluate(task_type=AITaskType.MARKET_CLASSIFICATION, task_value="low")
    assert decision.allowed is False
    assert decision.blocked_reason == "low_value_task_blocked"
