from __future__ import annotations

from typing import Any

from app.ai_brain.contracts import AIRequest, AITaskType
from app.ai_brain.service import HybridAIBrainService
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.social_neuron.contracts import NormalizedSocialEvent, SocialHypeScore, SocialMarketLink


class SocialAIContextAnalyzer:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None, ai_service: HybridAIBrainService | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._ai_service = ai_service or HybridAIBrainService(connection_factory=self._factory)

    def analyze_social_context(self, event: NormalizedSocialEvent, market_link: SocialMarketLink, hype_score: SocialHypeScore, *, allow_cloud: bool = False) -> dict[str, Any]:
        if market_link.confidence < 0.35 or hype_score.confidence < 0.25:
            return {"status": "SKIPPED", "reason": "low deterministic social value", "trade_fields": []}
        request = AIRequest(
            task_type=AITaskType.CONTEXT_SUMMARY,
            market_id=market_link.market_id,
            correlation_id=f"social_{event.social_event_id}",
            input_payload={
                "social_event_id": event.social_event_id,
                "normalized_text": event.normalized_text[:800],
                "market_id": market_link.market_id,
                "hype_pressure": hype_score.hype_pressure,
                "bot_risk": hype_score.bot_risk,
                "allow_cloud": False,
            },
            metadata={"source": "social_neuron", "allow_cloud_requested": allow_cloud},
        )
        try:
            response = self._ai_service.analyze(request)
            output = response.model_dump(mode="json") if hasattr(response, "model_dump") else dict(response)
        except Exception as exc:
            output = {"status": "UNAVAILABLE", "error": str(exc), "trade_fields": []}
        self._publish(EventType.SOCIAL_AI_ANALYZED, {"social_event_id": event.social_event_id, "market_id": market_link.market_id, "status": output.get("status", "COMPLETED")})
        return output

    def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="social_neuron", aggregate_type="market", aggregate_id=payload.get("market_id"), metadata={"non_trading_event": True})
        except Exception:
            pass
