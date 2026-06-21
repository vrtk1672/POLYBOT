from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.news_neuron.contracts import NewsDirection, NewsImpactScore, NewsMarketLink, NormalizedNewsEvent, bounded
from app.news_neuron.priced_in_detector import AlreadyPricedInDetector
from app.news_neuron.ttl_engine import NewsTTLEngine
from app.repositories.market_registry_repository import MarketRegistryRepository
from app.repositories.market_snapshot_v2_repository import MarketSnapshotV2Repository
from app.repositories.news_impact_repository import NewsImpactRepository


class NewsImpactScorer:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._repo = NewsImpactRepository()
        self._markets = MarketRegistryRepository()
        self._snapshots = MarketSnapshotV2Repository()
        self._priced_in = AlreadyPricedInDetector(connection_factory=self._factory)
        self._ttl = NewsTTLEngine()

    def score_news_impact(self, news_event: NormalizedNewsEvent | dict[str, Any], market_link: NewsMarketLink | dict[str, Any]) -> NewsImpactScore:
        event = news_event if isinstance(news_event, NormalizedNewsEvent) else _event_from_row(news_event)
        link = market_link if isinstance(market_link, NewsMarketLink) else _link_from_row(market_link)
        market = self._get_market(link.market_id)
        latest_snapshot = self._get_latest_snapshot(link.market_id)
        priced = self._priced_in.detect_already_priced_in(event.model_dump(), link.market_id)
        completeness = float((latest_snapshot or {}).get("data_completeness_score") or 0)
        completeness_factor = completeness / 100 if completeness > 1 else completeness
        closed_or_stale = bool((market or {}).get("closed") or (latest_snapshot or {}).get("stale"))
        strength = bounded(link.link_score * event.importance_score * (1 - float(priced["score"]) * 0.6))
        confidence = bounded(link.confidence * event.source_reliability * max(completeness_factor, 0.2))
        if closed_or_stale:
            confidence *= 0.25
            strength *= 0.25
        urgency = bounded(max(event.urgency_score, 0.2) * (0.5 if closed_or_stale else 1.0))
        ttl_seconds = self._ttl.compute_ttl_seconds(
            event.model_dump(mode="json"),
            {"confidence": confidence, "already_priced_in": priced["score"], "urgency": urgency},
            market,
        )
        risk_flags = list(priced.get("risk_flags") or [])
        if completeness_factor < 0.6:
            risk_flags.append("low_data_completeness")
        if closed_or_stale:
            risk_flags.append("closed_or_stale_market")
        return NewsImpactScore(
            impact_id=f"news_impact_{uuid4().hex}",
            news_event_id=event.news_event_id,
            market_id=link.market_id,
            direction=link.direction if isinstance(link.direction, NewsDirection) else NewsDirection(link.direction),
            strength=strength,
            confidence=confidence,
            urgency=urgency,
            already_priced_in=float(priced["score"]),
            ttl_seconds=ttl_seconds,
            source_reliability=event.source_reliability,
            reason=f"news impact from {link.link_reason or 'market link'}; priced_in={priced['reason']}",
            risk_flags=risk_flags,
        )

    def persist_impact_score(self, impact: NewsImpactScore) -> dict[str, Any]:
        if not self._factory.enabled:
            self._publish(impact)
            return impact.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            row = self._repo.insert_impact(conn, impact)
        self._publish(impact)
        return row

    def compute_signal(self, impact: NewsImpactScore) -> dict[str, Any]:
        return impact.signal

    def _get_market(self, market_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._markets.get_market(conn, market_id)

    def _get_latest_snapshot(self, market_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._snapshots.get_latest_snapshot(conn, market_id)

    def _publish(self, impact: NewsImpactScore) -> None:
        try:
            self._event_bus.publish(
                EventType.NEWS_IMPACT_SCORED.value,
                {
                    "impact_id": impact.impact_id,
                    "news_event_id": impact.news_event_id,
                    "market_id": impact.market_id,
                    "strength": impact.strength,
                    "confidence": impact.confidence,
                    "direction": impact.direction.value,
                },
                source_service="news_neuron",
                aggregate_type="market",
                aggregate_id=impact.market_id,
            )
        except Exception:
            pass


def _event_from_row(row: dict[str, Any]) -> NormalizedNewsEvent:
    from app.news_neuron.market_linker import _event_from_row as convert

    return convert(row)


def _link_from_row(row: dict[str, Any]) -> NewsMarketLink:
    from app.news_neuron.market_linker import _link_from_row as convert

    return convert(row)

