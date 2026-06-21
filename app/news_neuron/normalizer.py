from __future__ import annotations

import re
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.news_neuron.contracts import NormalizedNewsEvent, RawNewsEvent, bounded
from app.repositories.news_normalized_event_repository import NewsNormalizedEventRepository
from app.repositories.news_source_repository import NewsSourceRepository


class NewsNormalizer:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._repo = NewsNormalizedEventRepository()
        self._sources = NewsSourceRepository()

    def normalize_raw_event(self, raw_event: RawNewsEvent | dict[str, Any]) -> NormalizedNewsEvent:
        raw = raw_event if isinstance(raw_event, RawNewsEvent) else RawNewsEvent(**_raw_from_row(raw_event))
        text = " ".join(value for value in [raw.title, raw.summary, raw.body_text] if value)
        topics = infer_topics(text)
        category = _category_from_topics(topics) or _raw_category(raw.raw_payload)
        source_reliability = 0.5
        if self._factory.enabled:
            with self._factory.connect() as conn:
                source = self._sources.get_source(conn, raw.source_id)
                if source:
                    source_reliability = float(source.get("reliability_score") or 0.5)
        return NormalizedNewsEvent(
            raw_event_id=raw.raw_event_id,
            source_id=raw.source_id,
            title=raw.title,
            normalized_title=normalize_title(raw.title),
            summary=raw.summary,
            normalized_text=normalize_text(text),
            url=raw.url,
            published_at=raw.published_at,
            event_time=raw.published_at or raw.collected_at,
            category=category,
            entities=extract_basic_entities(text),
            topics=topics,
            language=raw.language,
            importance_score=compute_importance_score(raw),
            urgency_score=compute_urgency_score(raw),
            novelty_score=compute_novelty_score(raw),
            source_reliability=source_reliability,
        )

    def persist_normalized_event(self, event: NormalizedNewsEvent) -> dict[str, Any]:
        if not self._factory.enabled:
            self._publish(event, EventType.NEWS_EVENT_CREATED.value)
            self._publish(event, EventType.NEWS_EVENT_NORMALIZED.value)
            return event.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            row = self._repo.upsert_event(conn, event)
        self._publish(event, EventType.NEWS_EVENT_CREATED.value)
        self._publish(event, EventType.NEWS_EVENT_NORMALIZED.value)
        return row

    def _publish(self, event: NormalizedNewsEvent, event_type: str) -> None:
        try:
            self._event_bus.publish(
                event_type,
                {"news_event_id": event.news_event_id, "source_id": event.source_id, "title": event.title[:160], "category": event.category},
                source_service="news_neuron",
                aggregate_type="news_event",
                aggregate_id=event.news_event_id,
            )
        except Exception:
            pass


def normalize_title(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s$-]", " ", text.lower())).strip()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def extract_basic_entities(text: str) -> list[str]:
    matches = set(re.findall(r"\b(?:BTC|ETH|SOL|SEC|ETF|NBA|NFL|FIFA|Trump|Biden|Israel|Ukraine|Russia|China|Fed|CPI)\b", text, flags=re.I))
    matches.update(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", text))
    return sorted({match.strip() for match in matches if len(match.strip()) > 2})[:20]


def infer_topics(text: str) -> list[str]:
    lower = text.lower()
    topic_keywords = {
        "crypto": ("btc", "bitcoin", "eth", "ethereum", "crypto", "solana"),
        "politics": ("election", "president", "senate", "poll", "vote"),
        "sports": ("nba", "nfl", "game", "match", "team", "score"),
        "legal": ("court", "judge", "lawsuit", "ruling", "trial"),
        "weather": ("hurricane", "storm", "rain", "temperature", "weather"),
        "macro": ("fed", "cpi", "inflation", "rates", "jobs"),
        "security": ("hack", "exploit", "breach", "attack"),
        "geopolitics": ("war", "ceasefire", "israel", "ukraine", "russia", "china"),
    }
    return [topic for topic, words in topic_keywords.items() if any(word in lower for word in words)]


def compute_importance_score(raw_event: RawNewsEvent) -> float:
    text = f"{raw_event.title} {raw_event.summary or ''}".lower()
    score = 0.35
    if any(word in text for word in ("breaking", "urgent", "exclusive", "official", "confirmed")):
        score += 0.25
    if raw_event.url:
        score += 0.1
    if raw_event.summary:
        score += 0.1
    return bounded(score)


def compute_urgency_score(raw_event: RawNewsEvent) -> float:
    text = f"{raw_event.title} {raw_event.summary or ''}".lower()
    score = 0.25
    if any(word in text for word in ("breaking", "urgent", "live", "now", "just in")):
        score += 0.45
    if any(word in text for word in ("btc", "crypto", "sports", "game")):
        score += 0.15
    return bounded(score)


def compute_novelty_score(raw_event: RawNewsEvent) -> float:
    return 0.6 if raw_event.external_id or raw_event.url else 0.45


def _category_from_topics(topics: list[str]) -> str | None:
    return topics[0] if topics else None


def _raw_category(raw_payload: dict[str, Any]) -> str | None:
    value = raw_payload.get("category")
    return str(value) if value else None


def _raw_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw_event_id": row["raw_event_id"],
        "source_id": row["source_id"],
        "external_id": row.get("external_id"),
        "url": row.get("url"),
        "title": row["title"],
        "summary": row.get("summary"),
        "body_text": row.get("body_text"),
        "author": row.get("author"),
        "published_at": row.get("published_at"),
        "collected_at": row.get("collected_at"),
        "language": row.get("language"),
        "content_hash": row.get("content_hash"),
        "raw_payload": row.get("raw_payload_json") or {},
    }

