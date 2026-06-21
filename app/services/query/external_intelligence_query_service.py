from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.external_events_normalized_repository import ExternalEventsNormalizedRepository
from app.repositories.external_raw_events_repository import ExternalRawEventsRepository
from app.repositories.intelligence_ingestion_runs_repository import IntelligenceIngestionRunsRepository
from app.repositories.intelligence_sources_repository import IntelligenceSourcesRepository


class ExternalIntelligenceQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._sources = IntelligenceSourcesRepository()
        self._runs = IntelligenceIngestionRunsRepository()
        self._raw_events = ExternalRawEventsRepository()
        self._normalized_events = ExternalEventsNormalizedRepository()

    def list_intelligence_sources(self) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._sources.list_all(conn)
        return [dict(row) for row in rows]

    def get_ingestion_run_summary(self, intelligence_ingestion_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, intelligence_ingestion_run_id)
            if run is None:
                return None
            raw_rows = self._raw_events.list_for_run(conn, intelligence_ingestion_run_id)
            normalized_rows = self._normalized_events.list_for_run(conn, intelligence_ingestion_run_id)

        status_counts: dict[str, int] = {}
        for row in normalized_rows:
            status = str(row["status"])
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "run": dict(run),
            "raw_count": len(raw_rows),
            "normalized_count": len(normalized_rows),
            "normalized_status_counts": status_counts,
        }

    def list_raw_events_for_run(self, intelligence_ingestion_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._raw_events.list_for_run(conn, intelligence_ingestion_run_id)
        return [dict(row) for row in rows]

    def list_normalized_events_for_run(self, intelligence_ingestion_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._normalized_events.list_for_run(conn, intelligence_ingestion_run_id)
        return [dict(row) for row in rows]

    def list_recent_normalized_events(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._normalized_events.list_recent(conn, limit)
        return [dict(row) for row in rows]

    def find_duplicates_by_dedupe_key(self, dedupe_key: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._normalized_events.find_by_dedupe_key(conn, dedupe_key)
        return [dict(row) for row in rows]
