from __future__ import annotations

from app.ai_brain.contracts import AICaseFile, AIModelRoute, AIModelTier, AITaskType, normalize_task_type


LOCAL_FAST_MODEL = "qwen3:8b"
LOCAL_PRIMARY_MODEL = "qwen3:14b"
LOCAL_REASONING_MODEL = "deepseek-r1:14b"
CLOUD_MODEL = "cloud-critical-reasoner"


class AIModelRouter:
    def route(
        self,
        task_type: AITaskType | str,
        *,
        allow_cloud: bool = False,
        data_completeness_score: float | None = None,
        local_confidence: float | None = None,
        budget_cloud_allowed: bool = False,
        case_file: AICaseFile | None = None,
    ) -> AIModelRoute:
        task = normalize_task_type(task_type)
        completeness = data_completeness_score
        if completeness is None and case_file is not None:
            completeness = case_file.data_completeness_score
        completeness = float(completeness if completeness is not None else 100.0)

        if task == AITaskType.CASE_FILE_BUILD:
            return AIModelRoute(
                task_type=task,
                selected_tier=AIModelTier.LOCAL_FAST,
                selected_model="deterministic",
                provider="deterministic",
                reason="case files are built deterministically from V2.2 data",
                cloud_allowed=False,
                budget_required=False,
            )
        if task in {AITaskType.MARKET_CLASSIFICATION, AITaskType.NEWS_DEDUP}:
            return AIModelRoute(
                task_type=task,
                selected_tier=AIModelTier.LOCAL_FAST,
                selected_model=LOCAL_FAST_MODEL,
                provider="local",
                reason="fast local classification/dedup task",
            )
        if task in {
            AITaskType.RULES_SUMMARY,
            AITaskType.MARKET_LINKING,
            AITaskType.CONTEXT_SUMMARY,
            AITaskType.WORDING_RISK_PRECHECK,
        }:
            return AIModelRoute(
                task_type=task,
                selected_tier=AIModelTier.LOCAL_PRIMARY,
                selected_model=LOCAL_PRIMARY_MODEL,
                provider="local",
                reason="primary local semantic task",
            )

        cloud_allowed = (
            allow_cloud
            and budget_cloud_allowed
            and completeness >= 75
            and (local_confidence is None or local_confidence < 0.65)
            and task in {AITaskType.CONTRADICTION_CHECK, AITaskType.TRAP_PRECHECK}
        )
        if cloud_allowed:
            return AIModelRoute(
                task_type=task,
                selected_tier=AIModelTier.CLOUD_ESCALATION,
                selected_model=CLOUD_MODEL,
                provider="cloud",
                reason="critical reasoning task met cloud escalation gates",
                cloud_allowed=True,
            )
        return AIModelRoute(
            task_type=task,
            selected_tier=AIModelTier.LOCAL_REASONING,
            selected_model=LOCAL_REASONING_MODEL,
            provider="local",
            reason="local reasoning selected; cloud blocked by default or policy",
            cloud_allowed=False,
        )
