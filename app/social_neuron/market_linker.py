from __future__ import annotations

import re
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.social_market_link_repository import SocialMarketLinkRepository
from app.repositories.social_normalized_event_repository import SocialNormalizedEventRepository
from app.social_neuron.contracts import NormalizedSocialEvent, SocialDirection, SocialMarketLink, bounded


class SocialMarketLinker:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repo = SocialMarketLinkRepository()
        self._events = SocialNormalizedEventRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def link_social_to_markets(self, event: NormalizedSocialEvent, *, limit: int = 20) -> list[SocialMarketLink]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            markets = conn.execute("SELECT market_id, question, category, market_family, closed, active FROM markets_v2 ORDER BY last_seen_at DESC LIMIT %s", (limit * 5,)).fetchall()
            blocked = {row["market_id"] for row in conn.execute("SELECT DISTINCT market_id FROM compliance_blocks WHERE active = true AND severity = 'BLOCKING'").fetchall()} if self._table_exists(conn, "compliance_blocks") else set()
        links: list[SocialMarketLink] = []
        for market in markets:
            link = self.score_market_link(event, market, compliance_blocked=market["market_id"] in blocked)
            if link.link_score >= 0.25:
                self.persist_market_link(link)
                links.append(link)
        return links[:limit]

    def score_market_link(self, event: NormalizedSocialEvent, market: dict[str, Any], *, compliance_blocked: bool = False) -> SocialMarketLink:
        terms = self.extract_market_terms(market)
        text_terms = set(re.findall(r"[a-z0-9]+", event.normalized_text.lower()))
        matches = sorted(terms & text_terms)
        entity_matches = sorted(set(entity.lower() for entity in event.entities) & terms)
        crypto_match = bool({"btc", "bitcoin"} & text_terms and "btc" in terms)
        score = 0.0
        if matches:
            score += min(0.55, 0.12 * len(matches))
        if entity_matches:
            score += 0.2
        if crypto_match:
            score += 0.35
        if event.category and market.get("category") == event.category:
            score += 0.15
        if market.get("closed") or not market.get("active"):
            score *= 0.35
        if compliance_blocked:
            score *= 0.45
        score = bounded(score)
        direction = SocialDirection.UNKNOWN
        if any(term in event.normalized_text for term in ("yes", "support", "passes", "wins")):
            direction = SocialDirection.YES
        elif any(term in event.normalized_text for term in ("no", "fails", "blocked", "oppose")):
            direction = SocialDirection.NO
        return SocialMarketLink(
            social_event_id=event.social_event_id,
            market_id=market["market_id"],
            link_score=score,
            sentiment_direction=direction,
            confidence=bounded(score * (0.75 if not compliance_blocked else 0.45)),
            link_reason="deterministic social/market term match" if score >= 0.25 else "weak or unrelated social item",
            matched_entities=entity_matches,
            matched_terms=matches,
        )

    def extract_market_terms(self, market: dict[str, Any]) -> set[str]:
        text = " ".join(str(market.get(key) or "") for key in ("market_id", "question", "category", "market_family")).lower()
        terms = set(re.findall(r"[a-z0-9]+", text))
        if "bitcoin" in terms:
            terms.add("btc")
        if "btc" in terms:
            terms.add("bitcoin")
        return {term for term in terms if len(term) >= 3}

    def persist_market_link(self, link: SocialMarketLink) -> None:
        if self._factory.enabled:
            with self._factory.connect() as conn:
                self._repo.insert_link(conn, link)
                self._events.mark_linked(conn, link.social_event_id)
                conn.commit()
        self._publish(EventType.SOCIAL_MARKET_LINKED, {"social_event_id": link.social_event_id, "market_id": link.market_id, "link_score": link.link_score, "confidence": link.confidence})

    def _table_exists(self, conn, table_name: str) -> bool:
        row = conn.execute("SELECT to_regclass(%s) AS table_name", (table_name,)).fetchone()
        return bool(row and row["table_name"])

    def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="social_neuron", aggregate_type="market", aggregate_id=payload.get("market_id"), metadata={"non_trading_event": True})
        except Exception:
            pass
