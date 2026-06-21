from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.repositories.ai_model_performance_repository import AIModelPerformanceRepository


class AIModelPerformanceTracker:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, repository: AIModelPerformanceRepository | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or AIModelPerformanceRepository()

    def record_result(self, **kwargs: Any) -> None:
        if not self._factory.enabled:
            return
        try:
            with self._factory.connect() as conn:
                self._repository.record_result(conn, **kwargs)
                conn.commit()
        except Exception:
            return

    def list_summary(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        try:
            with self._factory.connect() as conn:
                return [dict(row) for row in self._repository.list_summary(conn, limit=limit)]
        except Exception:
            return []
