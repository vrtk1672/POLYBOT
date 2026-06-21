from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.social_noise_repository import SocialNoiseRepository
from app.social_neuron.contracts import NormalizedSocialEvent, SocialNoiseScore, bounded


class BotSpamFilter:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repo = SocialNoiseRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def compute_spam_score(self, event: NormalizedSocialEvent) -> float:
        hashtag_pressure = max(0, len(event.hashtags) + len(event.cashtags) - 3) * 0.15
        promo = 0.3 if any(term in event.normalized_text for term in ("airdrop", "giveaway", "guaranteed", "100x", "click")) else 0
        low_content = 0.25 if len(event.normalized_text.split()) < 4 else 0
        return bounded(hashtag_pressure + promo + low_content)

    def compute_bot_risk(self, event: NormalizedSocialEvent) -> float:
        repeated = 0.25 if event.normalized_text.count("!") >= 3 else 0
        handle = 0.15 if event.author_handle and any(ch.isdigit() for ch in event.author_handle[-4:]) else 0
        return bounded(repeated + handle + self.compute_spam_score(event) * 0.5)

    def compute_duplicate_risk(self, event: NormalizedSocialEvent) -> float:
        return 0.6 if event.dedup_group_id else 0.0

    def compute_coordinated_activity_risk(self, events: list[NormalizedSocialEvent]) -> float:
        if len(events) < 3:
            return 0.0
        texts = [event.normalized_text for event in events]
        return bounded((len(texts) - len(set(texts))) / max(1, len(texts)))

    def compute_noise_score(self, event: NormalizedSocialEvent, *, market_id: str | None = None) -> SocialNoiseScore:
        return SocialNoiseScore(
            social_event_id=event.social_event_id,
            market_id=market_id,
            platform=event.platform,
            spam_score=self.compute_spam_score(event),
            bot_risk=self.compute_bot_risk(event),
            duplicate_risk=self.compute_duplicate_risk(event),
            coordinated_activity_risk=0.0,
            reason="deterministic bot/spam risk score",
        )

    def persist_noise_score(self, score: SocialNoiseScore) -> None:
        if self._factory.enabled:
            with self._factory.connect() as conn:
                self._repo.insert_score(conn, score)
                conn.commit()
        self._publish(EventType.SOCIAL_NOISE_SCORED, {"social_event_id": score.social_event_id, "market_id": score.market_id, "noise_score": score.noise_score, "bot_risk": score.bot_risk})

    def _publish(self, event_type: EventType, payload: dict) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="social_neuron", aggregate_type="social_event", aggregate_id=payload.get("social_event_id"), metadata={"non_trading_event": True})
        except Exception:
            pass
