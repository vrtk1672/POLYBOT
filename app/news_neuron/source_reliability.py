from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.news_neuron.contracts import bounded
from app.repositories.news_reliability_repository import NewsReliabilityRepository
from app.repositories.news_source_repository import NewsSourceRepository


class SourceReliabilityScorer:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._repo = NewsReliabilityRepository()
        self._sources = NewsSourceRepository()

    def get_source_reliability(self, source_id: str) -> float:
        if not self._factory.enabled:
            return 0.5
        with self._factory.connect() as conn:
            row = self._repo.get_reliability(conn, source_id)
            if row:
                return float(row["reliability_score"])
            source = self._sources.get_source(conn, source_id)
            return float(source["reliability_score"]) if source else 0.5

    def score_source_event(self, source: dict[str, Any] | None, event: dict[str, Any] | None = None) -> float:
        if not source:
            return 0.5
        base = float(source.get("reliability_score") or 0.5)
        score = base - min(float(source.get("error_count") or 0) * 0.05, 0.35)
        if event and event.get("linked"):
            score += 0.05
        return bounded(score)

    def update_source_reliability(self, source_id: str) -> float:
        if not self._factory.enabled:
            return 0.5
        with self._factory.connect() as conn, conn.transaction():
            source = self._sources.get_source(conn, source_id)
            if not source:
                return 0.5
            counts = conn.execute(
                """
                SELECT
                    COUNT(ne.*) AS total_events,
                    COUNT(nml.*) AS linked_events,
                    COUNT(ne.*) FILTER (WHERE ne.status = 'IGNORED') AS ignored_events
                FROM news_normalized_events ne
                LEFT JOIN news_market_links nml ON nml.news_event_id = ne.news_event_id
                WHERE ne.source_id = %s
                """,
                (source_id,),
            ).fetchone()
            total = int(counts["total_events"] or 0)
            linked = int(counts["linked_events"] or 0)
            ignored = int(counts["ignored_events"] or 0)
            errors = int(source.get("error_count") or 0)
            score = 0.5
            score += min(linked * 0.03, 0.25)
            score -= min(errors * 0.05, 0.3)
            score -= min(ignored * 0.02, 0.15)
            if total == 0:
                score = float(source.get("reliability_score") or 0.5)
            score = bounded(score)
            self._repo.upsert_reliability(
                conn,
                source_id=source_id,
                category=source.get("category"),
                total_events=total,
                linked_events=linked,
                ignored_events=ignored,
                error_count=errors,
                reliability_score=score,
            )
        self._publish(source_id, score)
        return score

    def compute_latency_score(self, source: dict[str, Any]) -> float:
        return 0.5 if source.get("last_success_at") is None else 0.75

    def compute_error_penalty(self, source: dict[str, Any]) -> float:
        return min(float(source.get("error_count") or 0) * 0.05, 0.35)

    def compute_linked_event_bonus(self, source: dict[str, Any]) -> float:
        return 0.05 if source else 0.0

    def _publish(self, source_id: str, score: float) -> None:
        try:
            self._event_bus.publish(
                EventType.NEWS_SOURCE_RELIABILITY_UPDATED.value,
                {"source_id": source_id, "reliability_score": score},
                source_service="news_neuron",
                aggregate_type="news_source",
                aggregate_id=source_id,
            )
        except Exception:
            pass

