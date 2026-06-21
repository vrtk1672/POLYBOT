from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.invalidation_reasonings_repository import InvalidationReasoningsRepository
from app.repositories.invalidation_reasoning_runs_repository import InvalidationReasoningRunsRepository
from app.repositories.resolution_analyses_repository import ResolutionAnalysesRepository


class InvalidationReasoningQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = InvalidationReasoningRunsRepository()
        self._reasonings = InvalidationReasoningsRepository()
        self._resolution_analyses = ResolutionAnalysesRepository()

    def get_invalidation_reasoning_run_summary(
        self,
        invalidation_reasoning_run_id: str,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, invalidation_reasoning_run_id)
            if run is None:
                return None
            rows = self._reasonings.list_for_run(conn, invalidation_reasoning_run_id)

        status_counts: dict[str, int] = {}
        thesis_counts: dict[str, int] = {}
        monitoring_counts: dict[str, int] = {}
        for row in rows:
            status = str(row["status"])
            status_counts[status] = status_counts.get(status, 0) + 1
            thesis = row["thesis_effect_class"]
            if thesis is not None:
                thesis_key = str(thesis)
                thesis_counts[thesis_key] = thesis_counts.get(thesis_key, 0) + 1
            monitoring = row["recommended_monitoring_class"]
            if monitoring is not None:
                monitoring_key = str(monitoring)
                monitoring_counts[monitoring_key] = monitoring_counts.get(monitoring_key, 0) + 1

        return {
            "run": dict(run),
            "reasoning_count": len(rows),
            "status_counts": status_counts,
            "thesis_effect_counts": thesis_counts,
            "monitoring_counts": monitoring_counts,
        }

    def list_invalidation_reasonings_for_run(self, invalidation_reasoning_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._reasonings.list_for_run(conn, invalidation_reasoning_run_id)
        return [dict(row) for row in rows]

    def get_invalidation_reasoning_details(self, invalidation_reasoning_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            row = self._reasonings.get_by_id(conn, invalidation_reasoning_id)
        return dict(row) if row is not None else None

    def list_invalidation_reasonings_for_market(self, market_id: str, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._reasonings.list_for_market(conn, market_id, limit)
        return [dict(row) for row in rows]

    def compare_invalidation_reasoning_to_resolution_analysis(
        self,
        invalidation_reasoning_id: str,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            reasoning = self._reasonings.get_by_id(conn, invalidation_reasoning_id)
            if reasoning is None:
                return None
            resolution = self._resolution_analyses.get_by_id(conn, str(reasoning["resolution_analysis_id"]))
        return {
            "reasoning": dict(reasoning),
            "resolution_analysis": dict(resolution) if resolution is not None else None,
        }
