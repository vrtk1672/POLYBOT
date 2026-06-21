from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.event_interpretation_runs_repository import EventInterpretationRunsRepository
from app.repositories.event_interpretations_repository import EventInterpretationsRepository


class EventInterpretationQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = EventInterpretationRunsRepository()
        self._interpretations = EventInterpretationsRepository()

    def get_interpretation_run_summary(self, interpretation_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, interpretation_run_id)
            if run is None:
                return None
            interpretations = self._interpretations.list_for_run(conn, interpretation_run_id)
        return {
            "run": dict(run),
            "status_counts": {
                "success": sum(1 for row in interpretations if row["status"] == "SUCCESS"),
                "parse_error": sum(1 for row in interpretations if row["status"] == "PARSE_ERROR"),
                "model_error": sum(1 for row in interpretations if row["status"] == "MODEL_ERROR"),
            },
        }

    def list_interpretations_for_run(self, interpretation_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._interpretations.list_for_run(conn, interpretation_run_id)
        return [dict(row) for row in rows]

    def get_interpretation_details(self, interpretation_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            row = self._interpretations.get_by_id(conn, interpretation_id)
        return dict(row) if row is not None else None

    def list_recent_interpretations(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._interpretations.list_recent(conn, limit)
        return [dict(row) for row in rows]

    def compare_interpretation_candidates_to_existing_market_ids(
        self,
        interpretation_id: str,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            interpretation = self._interpretations.get_by_id(conn, interpretation_id)
            if interpretation is None:
                return None
            candidates = list(interpretation["affected_market_candidates_json"] or [])
            matches: list[dict[str, object]] = []
            for candidate in candidates:
                market_id_hint = candidate.get("market_id_hint")
                if not market_id_hint:
                    continue
                decision = conn.execute(
                    """
                    SELECT DISTINCT market_id
                    FROM decision_ledger
                    WHERE market_id = %s
                    LIMIT 1
                    """,
                    (market_id_hint,),
                ).fetchone()
                if decision is not None:
                    matches.append({"market_id": decision["market_id"], "candidate": candidate})
        return {
            "interpretation": dict(interpretation),
            "matches": matches,
        }
