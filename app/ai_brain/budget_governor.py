from __future__ import annotations

from dataclasses import dataclass, field

from app.ai_brain.contracts import AICaseFile, AITaskType, normalize_task_type
from app.db.connection import DatabaseConnectionFactory
from app.repositories.ai_cost_repository import AICostRepository


@dataclass(slots=True)
class AIBudgetDecision:
    allowed: bool
    blocked_reason: str | None = None
    max_cost: float = 0.0
    cloud_allowed: bool = False
    local_allowed: bool = False
    budget_snapshot: dict[str, object] = field(default_factory=dict)


class AIBudgetGovernor:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        cost_repository: AICostRepository | None = None,
        min_data_completeness_for_local: float = 50.0,
        min_data_completeness_for_cloud: float = 75.0,
        max_daily_total_ai_cost: float = 1.0,
        max_daily_cloud_cost: float = 0.25,
        max_cloud_calls_per_day: int = 20,
        block_low_value_tasks: bool = False,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._cost_repository = cost_repository or AICostRepository()
        self.min_data_completeness_for_local = min_data_completeness_for_local
        self.min_data_completeness_for_cloud = min_data_completeness_for_cloud
        self.max_daily_total_ai_cost = max_daily_total_ai_cost
        self.max_daily_cloud_cost = max_daily_cloud_cost
        self.max_cloud_calls_per_day = max_cloud_calls_per_day
        self.block_low_value_tasks = block_low_value_tasks

    def evaluate(
        self,
        *,
        task_type: AITaskType | str,
        case_file: AICaseFile | None = None,
        cache_hit: bool = False,
        cloud_requested: bool = False,
        local_confidence: float | None = None,
        estimated_cost: float = 0.0,
        task_value: str = "normal",
    ) -> AIBudgetDecision:
        task = normalize_task_type(task_type)
        snapshot = self.get_budget_snapshot()
        if cache_hit:
            return AIBudgetDecision(False, "cache_hit", cloud_allowed=False, local_allowed=False, budget_snapshot=snapshot)
        if self.block_low_value_tasks and task_value == "low":
            return AIBudgetDecision(False, "low_value_task_blocked", cloud_allowed=False, local_allowed=False, budget_snapshot=snapshot)

        completeness = float(case_file.data_completeness_score if case_file else 100.0)
        market_closed = bool((case_file.metadata or {}).get("closed")) if case_file else False
        if market_closed:
            return AIBudgetDecision(False, "market_closed", budget_snapshot=snapshot)
        if case_file and case_file.stale_fields:
            return AIBudgetDecision(False, "stale_data", budget_snapshot=snapshot)
        if completeness < self.min_data_completeness_for_local:
            return AIBudgetDecision(False, "low_data_completeness", budget_snapshot=snapshot)
        if float(snapshot["total_cost_today"]) + estimated_cost > self.max_daily_total_ai_cost:
            return AIBudgetDecision(False, "daily_ai_budget_exceeded", budget_snapshot=snapshot)

        local_allowed = True
        cloud_allowed = False
        blocked_reason: str | None = None
        if cloud_requested:
            if completeness < self.min_data_completeness_for_cloud:
                blocked_reason = "cloud_blocked_low_data_completeness"
            elif float(snapshot["cloud_cost_today"]) + estimated_cost > self.max_daily_cloud_cost:
                blocked_reason = "cloud_daily_budget_exceeded"
            elif int(snapshot["cloud_calls_today"]) >= self.max_cloud_calls_per_day:
                blocked_reason = "cloud_call_limit_exceeded"
            elif local_confidence is not None and local_confidence >= 0.65:
                blocked_reason = "cloud_blocked_local_confidence_sufficient"
            else:
                cloud_allowed = True
        return AIBudgetDecision(
            allowed=local_allowed or cloud_allowed,
            blocked_reason=blocked_reason,
            max_cost=self.max_daily_total_ai_cost - float(snapshot["total_cost_today"]),
            cloud_allowed=cloud_allowed,
            local_allowed=local_allowed,
            budget_snapshot=snapshot,
        )

    def get_budget_snapshot(self) -> dict[str, object]:
        if not self._factory.enabled:
            return {"total_cost_today": 0.0, "cloud_cost_today": 0.0, "cloud_calls_today": 0}
        try:
            with self._factory.connect() as conn:
                totals = self._cost_repository.daily_totals(conn)
            return {
                "total_cost_today": totals["total_cost"],
                "cloud_cost_today": totals["cloud_cost"],
                "cloud_calls_today": totals["cloud_calls"],
            }
        except Exception:
            return {"total_cost_today": 0.0, "cloud_cost_today": 0.0, "cloud_calls_today": 0, "status": "unavailable"}
