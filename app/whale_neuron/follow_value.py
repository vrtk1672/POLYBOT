from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.whale_follow_decision_repository import WhaleFollowDecisionRepository
from app.whale_neuron.contracts import WhaleEvent, WhaleFollowDecision, WhaleFollowDecisionValue, WhaleMarketScore, WhaleProfile, bounded
from app.whale_neuron.redaction import redact_dict


class WhaleFollowValueScorer:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._repo = WhaleFollowDecisionRepository()

    def compute_follow_value(self, profile: WhaleProfile, event: WhaleEvent | None = None, market_score: WhaleMarketScore | None = None) -> WhaleFollowDecision:
        follow_value = self.compute_expected_usefulness(profile, market_score)
        if profile.sample_size < 3:
            decision = WhaleFollowDecisionValue.WATCH if (event and (event.size_usd or 0) >= 10000) else WhaleFollowDecisionValue.INSUFFICIENT_DATA
            follow_value = min(follow_value, 0.45)
            reason = "insufficient sample; large size is watch-only"
        elif profile.noise_score >= 0.7:
            decision = WhaleFollowDecisionValue.PENALIZE
            reason = "high whale noise"
        elif follow_value >= 0.7 and profile.noise_score <= 0.35:
            decision = WhaleFollowDecisionValue.FOLLOW
            reason = "enough history with high follow value and low noise"
        elif follow_value >= 0.45:
            decision = WhaleFollowDecisionValue.WATCH
            reason = "moderate whale usefulness"
        else:
            decision = WhaleFollowDecisionValue.IGNORE
            reason = "low whale usefulness"
        return WhaleFollowDecision(
            whale_id=profile.whale_id,
            market_id=market_score.market_id if market_score else event.market_id if event else None,
            whale_event_id=event.whale_event_id if event else None,
            decision=decision,
            follow_value=follow_value,
            noise_score=profile.noise_score,
            confidence=bounded(profile.confidence),
            reason=reason,
        )

    def compute_copy_worthy_score(self, profile: WhaleProfile) -> float:
        return bounded((profile.timing_quality * 0.45) + (profile.follow_value * 0.4) + ((1 - profile.noise_score) * 0.15)) if profile.sample_size >= 3 else 0.0

    def compute_expected_usefulness(self, profile: WhaleProfile, market_score: WhaleMarketScore | None = None) -> float:
        base = (profile.timing_quality * 0.35) + ((profile.hit_rate or 0.5) * 0.25) + ((1 - profile.noise_score) * 0.25) + (profile.copy_worthy_score * 0.15)
        if market_score:
            base = (base * 0.65) + (market_score.follow_value * 0.35)
        return bounded(base)

    def persist_follow_decision(self, decision: WhaleFollowDecision) -> dict[str, object]:
        if not self._factory.enabled:
            return decision.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            row = self._repo.insert_decision(conn, decision)
        self._event_bus.publish(EventType.WHALE_FOLLOW_DECIDED.value, redact_dict(decision.model_dump(mode="json")), "whale_neuron", aggregate_type="whale", aggregate_id=decision.whale_id)
        return row

