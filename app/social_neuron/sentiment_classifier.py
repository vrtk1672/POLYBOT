from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.social_sentiment_repository import SocialSentimentRepository
from app.social_neuron.contracts import NormalizedSocialEvent, SocialMarketLink, SocialSentiment, SocialSentimentScore


class SentimentClassifier:
    BULLISH = {"bullish", "moon", "pump", "rally", "breakout", "up", "higher", "long"}
    BEARISH = {"bearish", "dump", "crash", "down", "lower", "short", "selloff"}
    SUPPORT = {"yes", "support", "approve", "wins", "passes", "happen"}
    OPPOSE = {"no", "oppose", "reject", "fails", "blocked", "not happen"}

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repo = SocialSentimentRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def classify(self, event: NormalizedSocialEvent, market_link: SocialMarketLink | None = None) -> SocialSentimentScore:
        words = set(event.normalized_text.split())
        bullish = len(words & self.BULLISH)
        bearish = len(words & self.BEARISH)
        yes = len(words & self.SUPPORT)
        no = len(words & self.OPPOSE)
        sentiment = SocialSentiment.UNKNOWN
        score = 0.0
        if bullish > bearish:
            sentiment, score = SocialSentiment.BULLISH, min(1, 0.45 + 0.15 * bullish)
        elif bearish > bullish:
            sentiment, score = SocialSentiment.BEARISH, min(1, 0.45 + 0.15 * bearish)
        elif yes > no:
            sentiment, score = SocialSentiment.YES, min(1, 0.45 + 0.15 * yes)
        elif no > yes:
            sentiment, score = SocialSentiment.NO, min(1, 0.45 + 0.15 * no)
        elif bullish and bearish:
            sentiment, score = SocialSentiment.MIXED, 0.45
        else:
            sentiment, score = SocialSentiment.NEUTRAL, 0.25
        return SocialSentimentScore(
            social_event_id=event.social_event_id,
            market_id=market_link.market_id if market_link else None,
            sentiment=sentiment,
            sentiment_score=score,
            confidence=score,
            reason="deterministic social sentiment",
        )

    def persist_score(self, score: SocialSentimentScore) -> None:
        if self._factory.enabled:
            with self._factory.connect() as conn:
                self._repo.insert_score(conn, score)
                conn.commit()
        self._publish(EventType.SOCIAL_SENTIMENT_SCORED, {"social_event_id": score.social_event_id, "market_id": score.market_id, "sentiment": score.sentiment.value, "confidence": score.confidence})

    def _publish(self, event_type: EventType, payload: dict) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="social_neuron", aggregate_type="market", aggregate_id=payload.get("market_id"), metadata={"non_trading_event": True})
        except Exception:
            pass
