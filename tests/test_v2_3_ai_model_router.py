from __future__ import annotations

from app.ai_brain.contracts import AICaseFile, AIModelTier, AITaskType
from app.ai_brain.model_router import AIModelRouter


def test_classification_routes_to_qwen3_8b() -> None:
    route = AIModelRouter().route(AITaskType.MARKET_CLASSIFICATION)
    assert route.selected_tier == AIModelTier.LOCAL_FAST
    assert route.selected_model == "qwen3:8b"


def test_rules_summary_routes_to_qwen3_14b() -> None:
    route = AIModelRouter().route(AITaskType.RULES_SUMMARY)
    assert route.selected_tier == AIModelTier.LOCAL_PRIMARY
    assert route.selected_model == "qwen3:14b"


def test_trap_precheck_cloud_blocked_by_default_and_low_completeness() -> None:
    router = AIModelRouter()
    default_route = router.route(AITaskType.TRAP_PRECHECK)
    low_data_route = router.route(
        AITaskType.TRAP_PRECHECK,
        allow_cloud=True,
        budget_cloud_allowed=True,
        case_file=AICaseFile(data_completeness_score=50),
    )
    assert default_route.provider == "local"
    assert low_data_route.provider == "local"


def test_trap_precheck_cloud_allowed_only_with_gates() -> None:
    route = AIModelRouter().route(
        AITaskType.TRAP_PRECHECK,
        allow_cloud=True,
        budget_cloud_allowed=True,
        local_confidence=0.3,
        case_file=AICaseFile(data_completeness_score=90),
    )
    assert route.selected_tier == AIModelTier.CLOUD_ESCALATION
    assert route.cloud_allowed is True
