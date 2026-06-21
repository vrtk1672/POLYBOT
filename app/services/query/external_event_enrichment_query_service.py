from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.external_event_enrichment_runs_repository import (
    ExternalEventEnrichmentRunsRepository,
)
from app.repositories.external_event_enrichments_repository import ExternalEventEnrichmentsRepository


class ExternalEventEnrichmentQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = ExternalEventEnrichmentRunsRepository()
        self._enrichments = ExternalEventEnrichmentsRepository()

    def get_external_event_enrichment_run_summary(
        self,
        external_event_enrichment_run_id: str,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, external_event_enrichment_run_id)
            if run is None:
                return None
            rows = self._enrichments.list_for_run(conn, external_event_enrichment_run_id)

        status_counts: dict[str, int] = {}
        topic_counts: dict[str, int] = {}
        usability_counts: dict[str, int] = {}
        for row in rows:
            status = str(row["status"])
            status_counts[status] = status_counts.get(status, 0) + 1
            topic = row["topic_class"]
            if topic is not None:
                topic_key = str(topic)
                topic_counts[topic_key] = topic_counts.get(topic_key, 0) + 1
            usability = row["usability_hint_class"]
            if usability is not None:
                usability_key = str(usability)
                usability_counts[usability_key] = usability_counts.get(usability_key, 0) + 1

        return {
            "run": dict(run),
            "enrichment_count": len(rows),
            "status_counts": status_counts,
            "topic_counts": topic_counts,
            "usability_counts": usability_counts,
        }

    def list_enrichments_for_run(self, external_event_enrichment_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._enrichments.list_for_run(conn, external_event_enrichment_run_id)
        return [dict(row) for row in rows]

    def get_enrichment_details(self, external_event_enrichment_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            row = self._enrichments.get_by_id(conn, external_event_enrichment_id)
        return dict(row) if row is not None else None

    def list_enrichments_for_external_event(self, external_event_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._enrichments.list_for_external_event(conn, external_event_id)
        return [dict(row) for row in rows]

    def find_enrichments_by_topic(self, topic_class: str, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._enrichments.find_by_topic(conn, topic_class, limit)
        return [dict(row) for row in rows]
