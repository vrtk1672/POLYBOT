from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.social_narrative_repository import SocialNarrativeRepository
from app.social_neuron.contracts import NormalizedSocialEvent, SocialMarketLink, SocialNarrative, bounded, stable_hash


class NarrativeDetector:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repo = SocialNarrativeRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def build_narrative_key(self, events: list[NormalizedSocialEvent]) -> str:
        topics = sorted({topic for event in events for topic in event.topics + event.hashtags + event.cashtags})
        basis = topics or sorted(events[0].normalized_text.split()[:5])
        return stable_hash({"narrative": basis})[:24]

    def detect_narrative_for_event(self, event: NormalizedSocialEvent) -> SocialNarrative:
        key = self.build_narrative_key([event])
        title_terms = event.topics or event.hashtags or event.cashtags or event.normalized_text.split()[:4]
        strength = self.compute_narrative_strength([event])
        return SocialNarrative(
            narrative_key=key,
            title=" ".join(title_terms[:6]) or "social narrative",
            topics=event.topics,
            entities=event.entities,
            event_count=1,
            narrative_strength=strength,
            confidence=max(0.25, strength),
        )

    def update_narrative(self, event: NormalizedSocialEvent, market_links: list[SocialMarketLink]) -> SocialNarrative:
        narrative = self.detect_narrative_for_event(event)
        narrative.market_ids = sorted({link.market_id for link in market_links})
        if self._factory.enabled:
            with self._factory.connect() as conn:
                row = self._repo.upsert_narrative(conn, narrative)
                conn.commit()
            narrative.narrative_id = row["narrative_id"]
            narrative.event_count = row["event_count"]
            narrative.narrative_strength = float(row["narrative_strength"])
            narrative.confidence = float(row["confidence"])
        self._publish(EventType.SOCIAL_NARRATIVE_DETECTED, {"narrative_id": narrative.narrative_id, "narrative_key": narrative.narrative_key, "market_ids": narrative.market_ids, "narrative_strength": narrative.narrative_strength})
        return narrative

    def compute_narrative_strength(self, events: list[NormalizedSocialEvent]) -> float:
        unique_authors = len({event.author_handle for event in events if event.author_handle}) or len(events)
        topic_density = sum(len(event.topics) + len(event.hashtags) + len(event.cashtags) for event in events)
        spam_penalty = sum(event.spam_score + event.bot_risk for event in events) / max(1, len(events)) * 0.25
        return bounded(0.2 + 0.12 * len(events) + 0.08 * unique_authors + 0.04 * topic_density - spam_penalty)

    def mark_faded_narratives(self, older_than_seconds: int = 86400) -> int:
        if not self._factory.enabled:
            return 0
        threshold = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
        with self._factory.connect() as conn:
            result = conn.execute("UPDATE social_narratives SET status = 'FADED' WHERE status = 'ACTIVE' AND last_seen_at < %s", (threshold,))
            conn.commit()
            return result.rowcount or 0

    def _publish(self, event_type: EventType, payload: dict) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="social_neuron", aggregate_type="social_narrative", aggregate_id=payload.get("narrative_id"), metadata={"non_trading_event": True})
        except Exception:
            pass
