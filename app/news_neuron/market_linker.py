from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.news_neuron.contracts import NewsDirection, NewsMarketLink, NormalizedNewsEvent, bounded
from app.repositories.market_registry_repository import MarketRegistryRepository
from app.repositories.news_market_link_repository import NewsMarketLinkRepository


class NewsMarketLinker:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._markets = MarketRegistryRepository()
        self._links = NewsMarketLinkRepository()

    def link_news_to_markets(self, news_event: NormalizedNewsEvent | dict[str, Any], *, limit: int = 20) -> list[NewsMarketLink]:
        event = news_event if isinstance(news_event, NormalizedNewsEvent) else _event_from_row(news_event)
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            markets = self._markets.list_markets(conn, active=None, limit=500)
        links = [self.score_market_link(event, market) for market in markets]
        viable = [link for link in links if link.link_score >= 0.2]
        viable.sort(key=lambda link: (link.link_score, link.confidence), reverse=True)
        persisted: list[NewsMarketLink] = []
        for link in viable[:limit]:
            row = self.persist_market_link(link)
            persisted.append(_link_from_row(row))
        return persisted

    def score_market_link(self, event: NormalizedNewsEvent, market: dict[str, Any]) -> NewsMarketLink:
        news_terms = _terms(" ".join([event.normalized_title, event.normalized_text or "", " ".join(event.entities), " ".join(event.topics)]))
        market_terms = self.extract_market_terms(market)
        matched_terms = sorted(news_terms & market_terms)
        matched_entities = sorted(set(event.entities) & {term.upper() for term in market_terms})
        overlap_score = len(matched_terms) / max(len(market_terms), 1)
        category_bonus = 0.2 if event.category and event.category in {market.get("category"), market.get("market_family")} else 0.0
        entity_bonus = min(len(matched_entities) * 0.15, 0.3)
        score = bounded(overlap_score + category_bonus + entity_bonus)
        if market.get("closed") or market.get("active") is False:
            score *= 0.35
        confidence = bounded(score * (0.7 if market.get("closed") else 1.0))
        return NewsMarketLink(
            link_id=f"news_link_{uuid4().hex}",
            news_event_id=event.news_event_id,
            market_id=str(market["market_id"]),
            link_score=score,
            direction=NewsDirection.UNKNOWN,
            confidence=confidence,
            link_reason="term/category/entity overlap" if score >= 0.2 else "weak or unrelated match",
            matched_entities=matched_entities,
            matched_terms=matched_terms,
            method="rule_based",
        )

    def extract_market_terms(self, market: dict[str, Any]) -> set[str]:
        raw = " ".join(
            str(value or "")
            for value in [
                market.get("question"),
                market.get("slug"),
                market.get("category"),
                market.get("market_family"),
            ]
        )
        return _terms(raw)

    def match_entities(self, news_entities: list[str], market: dict[str, Any]) -> list[str]:
        terms = self.extract_market_terms(market)
        return sorted({entity for entity in news_entities if entity.lower() in terms or entity.upper() in {t.upper() for t in terms}})

    def match_topics(self, news_topics: list[str], market: dict[str, Any]) -> list[str]:
        terms = self.extract_market_terms(market)
        return sorted({topic for topic in news_topics if topic in terms or topic == market.get("category") or topic == market.get("market_family")})

    def persist_market_link(self, link: NewsMarketLink) -> dict[str, Any]:
        if not self._factory.enabled:
            self._publish(link)
            return link.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            row = self._links.insert_link(conn, link)
        self._publish(link)
        return row

    def _publish(self, link: NewsMarketLink) -> None:
        try:
            self._event_bus.publish(
                EventType.NEWS_MARKET_LINKED.value,
                {
                    "link_id": link.link_id,
                    "news_event_id": link.news_event_id,
                    "market_id": link.market_id,
                    "link_score": link.link_score,
                    "direction": link.direction.value,
                },
                source_service="news_neuron",
                aggregate_type="market",
                aggregate_id=link.market_id,
            )
        except Exception:
            pass


def _terms(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "from", "will", "this", "that", "market", "polymarket", "yes", "no"}
    return {term for term in re.findall(r"[a-zA-Z0-9]+", text.lower()) if len(term) > 2 and term not in stop}


def _event_from_row(row: dict[str, Any]) -> NormalizedNewsEvent:
    return NormalizedNewsEvent(
        news_event_id=row["news_event_id"],
        raw_event_id=row.get("raw_event_id"),
        source_id=row["source_id"],
        dedup_group_id=row.get("dedup_group_id"),
        title=row["title"],
        normalized_title=row["normalized_title"],
        summary=row.get("summary"),
        normalized_text=row.get("normalized_text"),
        url=row.get("url"),
        published_at=row.get("published_at"),
        event_time=row.get("event_time"),
        category=row.get("category"),
        entities=row.get("entities_json") or [],
        topics=row.get("topics_json") or [],
        language=row.get("language"),
        importance_score=float(row.get("importance_score") or 0),
        urgency_score=float(row.get("urgency_score") or 0),
        novelty_score=float(row.get("novelty_score") or 0),
        source_reliability=float(row.get("source_reliability") or 0.5),
        status=row.get("status") or "NORMALIZED",
    )


def _link_from_row(row: dict[str, Any]) -> NewsMarketLink:
    return NewsMarketLink(
        link_id=row["link_id"],
        news_event_id=row["news_event_id"],
        market_id=row["market_id"],
        link_score=float(row["link_score"] or 0),
        direction=NewsDirection(row["direction"]),
        confidence=float(row["confidence"] or 0),
        link_reason=row.get("link_reason"),
        matched_entities=row.get("matched_entities_json") or [],
        matched_terms=row.get("matched_terms_json") or [],
        method=row.get("method") or "rule_based",
    )

