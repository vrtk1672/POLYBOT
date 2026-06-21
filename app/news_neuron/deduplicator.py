from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.news_neuron.contracts import DedupGroup, NormalizedNewsEvent
from app.repositories.news_dedup_repository import NewsDedupRepository
from app.repositories.news_normalized_event_repository import NewsNormalizedEventRepository


class NewsDeduplicator:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._repo = NewsDedupRepository()
        self._events = NewsNormalizedEventRepository()

    def compute_group_hash(self, event: NormalizedNewsEvent) -> str:
        signature = self.compute_topic_signature(event)
        return hashlib.sha256(signature.encode("utf-8")).hexdigest()

    def compute_topic_signature(self, event: NormalizedNewsEvent) -> str:
        terms = _important_terms(" ".join([event.normalized_title, " ".join(event.topics), " ".join(event.entities)]))
        return " ".join(sorted(terms)[:12])

    def find_existing_group(self, event: NormalizedNewsEvent) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._repo.get_by_group_hash(conn, self.compute_group_hash(event))

    def deduplicate(self, event: NormalizedNewsEvent) -> DedupGroup:
        group_hash = self.compute_group_hash(event)
        topic_signature = self.compute_topic_signature(event)
        if not self._factory.enabled:
            return DedupGroup(
                dedup_group_id=f"news_dedup_{uuid4().hex}",
                canonical_news_event_id=event.news_event_id,
                group_hash=group_hash,
                topic_signature=topic_signature,
                event_count=1,
                sources=[event.source_id],
            )
        with self._factory.connect() as conn, conn.transaction():
            existing = self._repo.get_by_group_hash(conn, group_hash)
            if existing:
                sources = sorted(set((existing.get("sources_json") or []) + [event.source_id]))
                row = self._repo.increment_group(conn, existing["dedup_group_id"], sources)
                self._events.set_dedup_group(conn, event.news_event_id, existing["dedup_group_id"])
            else:
                group = DedupGroup(
                    dedup_group_id=f"news_dedup_{uuid4().hex}",
                    canonical_news_event_id=event.news_event_id,
                    group_hash=group_hash,
                    topic_signature=topic_signature,
                    event_count=1,
                    sources=[event.source_id],
                )
                row = self._repo.upsert_group(conn, group)
                self._events.set_dedup_group(conn, event.news_event_id, row["dedup_group_id"])
        self._publish(event.news_event_id, row["dedup_group_id"], row["event_count"])
        return DedupGroup(
            dedup_group_id=row["dedup_group_id"],
            canonical_news_event_id=row.get("canonical_news_event_id"),
            group_hash=row["group_hash"],
            topic_signature=row.get("topic_signature"),
            event_count=row["event_count"],
            sources=row.get("sources_json") or [],
        )

    def _publish(self, news_event_id: str, dedup_group_id: str, event_count: int) -> None:
        try:
            self._event_bus.publish(
                EventType.NEWS_EVENT_DEDUPED.value,
                {"news_event_id": news_event_id, "dedup_group_id": dedup_group_id, "event_count": event_count},
                source_service="news_neuron",
                aggregate_type="news_event",
                aggregate_id=news_event_id,
            )
        except Exception:
            pass


def _important_terms(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "from", "that", "this", "will", "after", "before", "says", "over", "into"}
    return {term for term in text.lower().replace("-", " ").split() if len(term) > 2 and term not in stop}

