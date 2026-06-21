from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.whale_market_score_repository import WhaleMarketScoreRepository
from app.whale_neuron.contracts import WhaleActionType, WhaleEvent, WhaleEventClassification, WhaleMarketScore, WhaleProfile, bounded
from app.whale_neuron.redaction import redact_dict


class WhaleMarketScorer:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._repo = WhaleMarketScoreRepository()

    def score_whale_for_market(self, event: WhaleEvent, profile: WhaleProfile, market_context: dict[str, Any] | None = None) -> WhaleMarketScore | None:
        if not event.market_id:
            return None
        context = market_context or self._load_market_context(event.market_id)
        presence = self.compute_whale_presence_score(event)
        conviction = self.compute_whale_conviction_score(event)
        alignment = self.compute_smart_whale_alignment(profile)
        reversal = self.compute_reversal_risk(event, profile)
        noise = self.compute_noise_penalty(profile)
        follow_value = bounded(((presence * 0.2) + (conviction * 0.2) + (alignment * 0.45) + ((1 - noise) * 0.15)) * (0.5 if context.get("compliance_blocked") else 1.0))
        confidence = bounded((event.confidence * 0.3) + (profile.confidence * 0.4) + ((1 - noise) * 0.2) + (0.1 if context.get("market_known") else 0))
        if context.get("closed") or context.get("low_completeness") or context.get("compliance_blocked"):
            confidence = bounded(confidence * 0.45)
        score = WhaleMarketScore(
            market_id=event.market_id,
            whale_id=event.whale_id or "unknown",
            whale_event_id=event.whale_event_id,
            side=event.side,
            whale_presence_score=presence,
            whale_conviction_score=conviction,
            smart_whale_alignment=alignment,
            whale_reversal_risk=reversal,
            follow_value=follow_value,
            noise_penalty=noise,
            confidence=confidence,
        )
        score.signal["size_usd"] = event.size_usd
        score.signal["reversal_risk"] = reversal
        score.signal["confidence"] = confidence
        return score

    def compute_whale_presence_score(self, event: WhaleEvent) -> float:
        return bounded((event.size_usd or event.notional or 0) / 25000)

    def compute_whale_conviction_score(self, event: WhaleEvent) -> float:
        return bounded(((event.size_usd or 0) / 50000) + (0.15 if event.price is not None else 0))

    def compute_smart_whale_alignment(self, profile: WhaleProfile) -> float:
        return bounded((profile.timing_quality * 0.45) + (profile.follow_value * 0.35) + (profile.copy_worthy_score * 0.2))

    def compute_reversal_risk(self, event: WhaleEvent, profile: WhaleProfile) -> float:
        base = 0.65 if event.action_type in {WhaleActionType.SELL, WhaleActionType.POSITION_CLOSE} or event.event_classification in {WhaleEventClassification.EXIT, WhaleEventClassification.DISTRIBUTION, WhaleEventClassification.REVERSAL} else 0.1
        return bounded(base + profile.reversal_risk_score * 0.25)

    def compute_noise_penalty(self, profile: WhaleProfile) -> float:
        return bounded(profile.noise_score)

    def create_whale_signal(self, score: WhaleMarketScore) -> dict[str, Any]:
        return redact_dict(score.signal)

    def persist_market_score(self, score: WhaleMarketScore) -> dict[str, Any]:
        if not self._factory.enabled:
            return score.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            row = self._repo.insert_score(conn, score)
        self._event_bus.publish(EventType.WHALE_MARKET_SCORED.value, redact_dict(score.model_dump(mode="json")), "whale_neuron", aggregate_type="market", aggregate_id=score.market_id)
        self._event_bus.publish(EventType.WHALE_SIGNAL_CREATED.value, self.create_whale_signal(score), "whale_neuron", aggregate_type="market", aggregate_id=score.market_id)
        return row

    def _load_market_context(self, market_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"market_known": False}
        try:
            with self._factory.connect() as conn:
                market = conn.execute("SELECT market_id, status FROM markets_v2 WHERE market_id = %s LIMIT 1", (market_id,)).fetchone()
                block = conn.execute("SELECT 1 FROM compliance_blocks WHERE market_id = %s AND active = true AND severity = 'BLOCKING' LIMIT 1", (market_id,)).fetchone()
                completeness = conn.execute("SELECT completeness_score FROM data_completeness_snapshots WHERE market_id = %s ORDER BY created_at DESC LIMIT 1", (market_id,)).fetchone()
            return {
                "market_known": bool(market),
                "closed": bool(market and str(market.get("status", "")).upper() in {"CLOSED", "RESOLVED"}),
                "compliance_blocked": bool(block),
                "low_completeness": bool(completeness and float(completeness.get("completeness_score") or 0) < 0.5),
            }
        except Exception:
            return {"market_known": False, "low_completeness": True}

