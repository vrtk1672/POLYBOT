from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.repositories.ai_cost_repository import AICostRepository


class AICostLedger:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, repository: AICostRepository | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or AICostRepository()

    def record_cost(self, **kwargs: Any) -> str | None:
        if not self._factory.enabled:
            return None
        try:
            with self._factory.connect() as conn:
                cost_id = self._repository.record_cost(conn, **kwargs)
                conn.commit()
                return cost_id
        except Exception:
            return None

    def summarize_costs(self, *, model: str | None = None, task_type: str | None = None) -> dict[str, Any]:
        if not self._factory.enabled:
            return {
                "total_estimated_cost": 0.0,
                "total_actual_cost": 0.0,
                "cloud_cost_today": 0.0,
                "cloud_calls_today": 0,
                "local_calls_today": 0,
                "cost_by_model": [],
                "cost_by_task": [],
            }
        try:
            with self._factory.connect() as conn:
                return self._repository.summarize_costs(conn, model=model, task_type=task_type)
        except Exception:
            return {
                "total_estimated_cost": 0.0,
                "total_actual_cost": 0.0,
                "cloud_cost_today": 0.0,
                "cloud_calls_today": 0,
                "local_calls_today": 0,
                "cost_by_model": [],
                "cost_by_task": [],
            }
