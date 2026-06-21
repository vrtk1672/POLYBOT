from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.external_event_enrichment import ExternalEventEnrichmentContract


class ExternalEventEnrichmentsRepository:
    def insert(self, conn: Connection, enrichment: ExternalEventEnrichmentContract) -> None:
        conn.execute(
            """
            INSERT INTO external_event_enrichments (
                id, external_event_enrichment_run_id, external_event_id, intelligence_source_id,
                normalized_title_snapshot, normalized_summary_snapshot, entities_json,
                topic_class, subtopic_class, contradiction_hint_class, novelty_hint_class,
                usability_hint_class, trust_weight_snapshot, enrichment_version,
                explanation_json, status, error_text
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            """,
            (
                enrichment.id,
                enrichment.external_event_enrichment_run_id,
                enrichment.external_event_id,
                enrichment.intelligence_source_id,
                enrichment.normalized_title_snapshot,
                enrichment.normalized_summary_snapshot,
                Jsonb(enrichment.entities_json),
                enrichment.topic_class,
                enrichment.subtopic_class,
                enrichment.contradiction_hint_class,
                enrichment.novelty_hint_class,
                enrichment.usability_hint_class,
                enrichment.trust_weight_snapshot,
                enrichment.enrichment_version,
                Jsonb(enrichment.explanation_json),
                enrichment.status,
                enrichment.error_text,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM external_event_enrichments
            WHERE external_event_enrichment_run_id = %s
            ORDER BY created_at ASC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, enrichment_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM external_event_enrichments
            WHERE id = %s
            LIMIT 1
            """,
            (enrichment_id,),
        ).fetchone()

    def list_for_external_event(self, conn: Connection, external_event_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM external_event_enrichments
            WHERE external_event_id = %s
            ORDER BY created_at DESC
            """,
            (external_event_id,),
        ).fetchall()

    def find_by_topic(self, conn: Connection, topic_class: str, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM external_event_enrichments
            WHERE topic_class = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (topic_class, limit),
        ).fetchall()
