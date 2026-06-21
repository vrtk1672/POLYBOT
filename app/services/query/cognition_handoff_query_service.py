from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.cognition_handoff_candidates_repository import CognitionHandoffCandidatesRepository
from app.repositories.cognition_handoff_runs_repository import CognitionHandoffRunsRepository


class CognitionHandoffQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = CognitionHandoffRunsRepository()
        self._candidates = CognitionHandoffCandidatesRepository()

    def get_cognition_handoff_run_summary(self, cognition_handoff_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, cognition_handoff_run_id)
            if run is None:
                return None
            rows = self._candidates.list_for_run(conn, cognition_handoff_run_id)

        decision_counts: dict[str, int] = {}
        priority_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for row in rows:
            decision = row["handoff_decision_class"]
            if decision is not None:
                decision_key = str(decision)
                decision_counts[decision_key] = decision_counts.get(decision_key, 0) + 1
            priority = row["handoff_priority_class"]
            if priority is not None:
                priority_key = str(priority)
                priority_counts[priority_key] = priority_counts.get(priority_key, 0) + 1
            status = str(row["status"])
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "run": dict(run),
            "candidate_count": len(rows),
            "decision_counts": decision_counts,
            "priority_counts": priority_counts,
            "status_counts": status_counts,
        }

    def list_handoff_candidates_for_run(self, cognition_handoff_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._candidates.list_for_run(conn, cognition_handoff_run_id)
        return [dict(row) for row in rows]

    def get_handoff_candidate_details(self, cognition_handoff_candidate_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            row = self._candidates.get_by_id(conn, cognition_handoff_candidate_id)
        return dict(row) if row is not None else None

    def list_handoff_candidates_for_external_event(self, external_event_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._candidates.list_for_external_event(conn, external_event_id)
        return [dict(row) for row in rows]

    def list_pending_handoff_candidates(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._candidates.list_pending(conn, limit)
        return [dict(row) for row in rows]
