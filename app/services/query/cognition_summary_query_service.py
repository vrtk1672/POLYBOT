from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.cognition_summaries_repository import CognitionSummariesRepository
from app.repositories.cognition_summary_runs_repository import CognitionSummaryRunsRepository
from app.repositories.invalidation_reasonings_repository import InvalidationReasoningsRepository


class CognitionSummaryQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = CognitionSummaryRunsRepository()
        self._summaries = CognitionSummariesRepository()
        self._reasonings = InvalidationReasoningsRepository()

    def get_cognition_summary_run_summary(self, cognition_summary_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, cognition_summary_run_id)
            if run is None:
                return None
            rows = self._summaries.list_for_run(conn, cognition_summary_run_id)

        status_counts: dict[str, int] = {}
        conclusion_counts: dict[str, int] = {}
        usability_counts: dict[str, int] = {}
        for row in rows:
            status = str(row["status"])
            status_counts[status] = status_counts.get(status, 0) + 1
            conclusion = row["cognition_conclusion_class"]
            if conclusion is not None:
                conclusion_key = str(conclusion)
                conclusion_counts[conclusion_key] = conclusion_counts.get(conclusion_key, 0) + 1
            usability = row["usability_class"]
            if usability is not None:
                usability_key = str(usability)
                usability_counts[usability_key] = usability_counts.get(usability_key, 0) + 1

        return {
            "run": dict(run),
            "summary_count": len(rows),
            "status_counts": status_counts,
            "conclusion_counts": conclusion_counts,
            "usability_counts": usability_counts,
        }

    def list_cognition_summaries_for_run(self, cognition_summary_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._summaries.list_for_run(conn, cognition_summary_run_id)
        return [dict(row) for row in rows]

    def get_cognition_summary_details(self, cognition_summary_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            row = self._summaries.get_by_id(conn, cognition_summary_id)
        return dict(row) if row is not None else None

    def list_cognition_summaries_for_market(self, market_id: str, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._summaries.list_for_market(conn, market_id, limit)
        return [dict(row) for row in rows]

    def compare_cognition_summary_to_invalidation_reasoning(self, cognition_summary_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            summary = self._summaries.get_by_id(conn, cognition_summary_id)
            if summary is None:
                return None
            reasoning = self._reasonings.get_by_id(conn, str(summary["invalidation_reasoning_id"]))
        return {
            "cognition_summary": dict(summary),
            "invalidation_reasoning": dict(reasoning) if reasoning is not None else None,
        }
