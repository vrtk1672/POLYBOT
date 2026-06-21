from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.social_hype_repository import SocialHypeRepository
from app.social_neuron.contracts import SocialHypeScore, SocialNarrative, SocialSentiment, SocialSentimentScore, bounded
from app.social_neuron.mention_velocity import MentionVelocityTracker


class HypePressureScorer:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repo = SocialHypeRepository()
        self._velocity = MentionVelocityTracker(connection_factory=self._factory)
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def score_hype_pressure(self, market_id: str, *, window_seconds: int = 900, sentiment_score: SocialSentimentScore | None = None, narrative: SocialNarrative | None = None) -> SocialHypeScore:
        stats = self._velocity.compute_mentions_velocity(market_id, window_seconds)
        mention_component = bounded(stats["mentions_velocity"] / 3)
        author_component = bounded(stats["unique_author_count"] / 10)
        narrative_strength = narrative.narrative_strength if narrative else 0.0
        bot_risk = bounded(stats["spam_ratio"])
        sentiment_confidence = sentiment_score.confidence if sentiment_score else 0.0
        hype = bounded((mention_component * 0.45) + (author_component * 0.2) + (narrative_strength * 0.25) + (sentiment_confidence * 0.1) - (bot_risk * 0.25))
        confidence = bounded(0.2 + author_component * 0.25 + sentiment_confidence * 0.25 + narrative_strength * 0.2 - bot_risk * 0.25)
        return SocialHypeScore(
            market_id=market_id,
            window_seconds=window_seconds,
            mention_count=stats["mention_count"],
            unique_author_count=stats["unique_author_count"],
            mentions_velocity=stats["mentions_velocity"],
            velocity_zscore=stats["velocity_zscore"],
            hype_pressure=hype,
            sentiment=sentiment_score.sentiment if sentiment_score else SocialSentiment.UNKNOWN,
            sentiment_confidence=sentiment_confidence,
            bot_risk=bot_risk,
            spam_ratio=stats["spam_ratio"],
            narrative_strength=narrative_strength,
            confidence=confidence,
        )

    def persist_hype_score(self, score: SocialHypeScore) -> None:
        if self._factory.enabled:
            with self._factory.connect() as conn:
                self._repo.insert_score(conn, score)
                conn.commit()
        payload = {"market_id": score.market_id, "hype_id": score.hype_id, "hype_pressure": score.hype_pressure, "confidence": score.confidence}
        self._publish(EventType.SOCIAL_HYPE_SCORED, payload)
        self._publish(EventType.SOCIAL_SIGNAL_CREATED, {"market_id": score.market_id, "hype_id": score.hype_id, "signal": score.signal})

    def _publish(self, event_type: EventType, payload: dict) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="social_neuron", aggregate_type="market", aggregate_id=payload.get("market_id"), metadata={"non_trading_event": True})
        except Exception:
            pass
