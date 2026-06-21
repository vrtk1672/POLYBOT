from __future__ import annotations

from typing import Any

from app.ai_brain.contracts import AIRequest, AITaskType
from app.ai_brain.service import HybridAIBrainService
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.whale_neuron.contracts import WhaleEvent, WhaleMarketScore, WhaleProfile
from app.whale_neuron.redaction import redact_dict


class WhaleAIContextAnalyzer:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None, ai_service: HybridAIBrainService | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._ai = ai_service or HybridAIBrainService(connection_factory=self._factory, event_bus=self._event_bus)

    def analyze_whale_context(self, event: WhaleEvent, profile: WhaleProfile, market_score: WhaleMarketScore | None = None, *, allow_cloud: bool = False) -> dict[str, Any]:
        if allow_cloud and (not event.market_id or event.confidence < 0.5):
            allow_cloud = False
        request = {
            "event": event.model_dump(mode="json"),
            "profile": profile.model_dump(mode="json"),
            "market_score": market_score.model_dump(mode="json") if market_score else None,
            "instruction": "Summarize whale behavior only. Do not create trades, orders, order intents, risk approvals, or exits.",
        }
        try:
            result = self._ai.analyze(
                AIRequest(
                    task_type=AITaskType.CONTEXT_SUMMARY,
                    market_id=event.market_id,
                    event_id=event.whale_event_id,
                    input_payload=redact_dict(request),
                    metadata={"node": "whale"},
                ),
                allow_cloud=allow_cloud,
                reason="v2.7 whale context enrichment",
            )
            payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
        except Exception as exc:
            payload = {"status": "UNAVAILABLE", "reason": str(exc), "trade_fields_created": False}
        payload = redact_dict(payload)
        self._event_bus.publish(EventType.WHALE_AI_ANALYZED.value, {"whale_event_id": event.whale_event_id, "whale_id": event.whale_id, "status": payload.get("status", "OK")}, "whale_neuron", aggregate_type="whale", aggregate_id=event.whale_id or "unknown")
        return payload
