from __future__ import annotations

import re
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.social_normalized_event_repository import SocialNormalizedEventRepository
from app.social_neuron.contracts import NormalizedSocialEvent, RawSocialEvent, bounded


class SocialNormalizer:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._events = SocialNormalizedEventRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def normalize_raw_event(self, raw_event: RawSocialEvent | dict[str, Any]) -> NormalizedSocialEvent:
        event = raw_event if isinstance(raw_event, RawSocialEvent) else RawSocialEvent(
            raw_social_event_id=raw_event["raw_social_event_id"],
            source_id=raw_event["source_id"],
            platform=raw_event.get("platform", "manual"),
            text=raw_event["text"],
            raw_text=raw_event.get("raw_text"),
            author_handle=raw_event.get("author_handle"),
            url=raw_event.get("url"),
            published_at=raw_event.get("published_at"),
            collected_at=raw_event.get("collected_at"),
            engagement=raw_event.get("engagement_json") or {},
            content_hash=raw_event.get("content_hash"),
            raw_payload=raw_event.get("raw_payload_json") or {},
        )
        normalized = self.normalize_text(event.text)
        return NormalizedSocialEvent(
            raw_social_event_id=event.raw_social_event_id,
            source_id=event.source_id,
            platform=event.platform,
            text=event.text,
            normalized_text=normalized,
            author_handle=event.author_handle,
            url=event.url,
            published_at=event.published_at,
            category=self.infer_category(None, event),
            entities=self.extract_basic_entities(event.text),
            topics=self.infer_topics(event.text),
            hashtags=self.extract_hashtags(event.text),
            cashtags=self.extract_cashtags(event.text),
            language=event.language,
            engagement_score=self.compute_engagement_score(event),
            influence_score=self.compute_influence_score(event),
            novelty_score=self.compute_novelty_score(event),
        )

    def normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.lower().strip())

    def extract_basic_entities(self, text: str) -> list[str]:
        entities = set(re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", text))
        entities.update(tag.upper() for tag in self.extract_cashtags(text))
        return sorted(entities)

    def extract_hashtags(self, text: str) -> list[str]:
        return sorted({tag.lower() for tag in re.findall(r"#([A-Za-z0-9_]+)", text)})

    def extract_cashtags(self, text: str) -> list[str]:
        return sorted({tag.upper() for tag in re.findall(r"\$([A-Za-z]{2,10})", text)})

    def infer_category(self, source: dict[str, Any] | None, raw_event: RawSocialEvent) -> str | None:
        text = raw_event.text.lower()
        if any(term in text for term in ("btc", "bitcoin", "eth", "crypto", "$btc")):
            return "crypto"
        if any(term in text for term in ("election", "president", "senate", "trump", "biden")):
            return "politics"
        if any(term in text for term in ("game", "team", "score", "nba", "nfl")):
            return "sports"
        return source.get("category") if source else None

    def infer_topics(self, text: str) -> list[str]:
        lowered = text.lower()
        topics = []
        for topic in ("btc", "bitcoin", "crypto", "election", "sports", "weather", "court", "macro"):
            if topic in lowered:
                topics.append(topic)
        return sorted(set(topics))

    def compute_engagement_score(self, raw_event: RawSocialEvent) -> float:
        engagement = raw_event.engagement or {}
        total = sum(float(engagement.get(key, 0) or 0) for key in ("likes", "shares", "reposts", "comments", "views"))
        return bounded(total / 1000)

    def compute_influence_score(self, raw_event: RawSocialEvent) -> float:
        followers = float((raw_event.engagement or {}).get("followers", 0) or 0)
        return bounded(followers / 100000)

    def compute_novelty_score(self, raw_event: RawSocialEvent) -> float:
        return 0.5 if raw_event.url else 0.35

    def persist_normalized_event(self, event: NormalizedSocialEvent) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._events.upsert_event(conn, event)
            conn.commit()
        self._publish(EventType.SOCIAL_EVENT_CREATED, {"social_event_id": event.social_event_id, "source_id": event.source_id, "platform": event.platform.value})
        self._publish(EventType.SOCIAL_EVENT_NORMALIZED, {"social_event_id": event.social_event_id, "topics": event.topics, "hashtags": event.hashtags, "cashtags": event.cashtags})
        return row

    def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="social_neuron", aggregate_type="social_event", aggregate_id=payload.get("social_event_id"), metadata={"non_trading_event": True})
        except Exception:
            pass
