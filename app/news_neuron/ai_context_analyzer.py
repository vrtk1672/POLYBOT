from __future__ import annotations

from typing import Any

from app.ai_brain.contracts import AIRequest, AITaskType
from app.ai_brain.service import HybridAIBrainService
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.news_neuron.contracts import NewsImpactScore, NewsMarketLink, NormalizedNewsEvent
from app.repositories.news_ai_analysis_repository import NewsAIAnalysisRepository


class NewsAIContextAnalyzer:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
        ai_service: HybridAIBrainService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._ai_service = ai_service or HybridAIBrainService(connection_factory=self._factory, event_bus=self._event_bus)
        self._repo = NewsAIAnalysisRepository()

    def analyze_news_context(
        self,
        news_event: NormalizedNewsEvent,
        market_link: NewsMarketLink,
        impact_score: NewsImpactScore,
        *,
        allow_cloud: bool = False,
    ) -> dict[str, Any]:
        if impact_score.confidence < 0.25 or impact_score.strength < 0.25:
            return {"status": "SKIPPED", "reason": "low_value_news_ai_call"}
        request = AIRequest(
            task_type=AITaskType.CONTEXT_SUMMARY,
            market_id=market_link.market_id,
            input_payload={
                "news_event_id": news_event.news_event_id,
                "title": news_event.title,
                "summary": news_event.summary,
                "market_link": market_link.model_dump(mode="json"),
                "impact": impact_score.model_dump(mode="json"),
                "instruction": "summarize news context only; do not create trade decisions",
            },
            metadata={"source": "news_neuron"},
        )
        try:
            response = self._ai_service.analyze(request, allow_cloud=allow_cloud, reason="news context analysis")
            analysis = {
                "status": "COMPLETED",
                "ai_request_id": response.ai_request_id,
                "structured_output": response.structured_output,
                "confidence": response.confidence,
                "risk_flags": response.risk_flags,
            }
        except Exception as exc:
            analysis = {"status": "UNAVAILABLE", "reason": str(exc), "confidence": 0.0, "risk_flags": ["ai_unavailable"]}
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                row = self._repo.insert_analysis(
                    conn,
                    news_event_id=news_event.news_event_id,
                    market_id=market_link.market_id,
                    ai_request_id=analysis.get("ai_request_id"),
                    task_type=AITaskType.CONTEXT_SUMMARY.value,
                    analysis=analysis,
                    confidence=float(analysis.get("confidence") or 0),
                    risk_flags=list(analysis.get("risk_flags") or []),
                )
            analysis["news_ai_analysis_id"] = row["news_ai_analysis_id"]
        self._publish(news_event.news_event_id, market_link.market_id, analysis)
        return analysis

    def _publish(self, news_event_id: str, market_id: str, analysis: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(
                EventType.NEWS_AI_ANALYZED.value,
                {
                    "news_event_id": news_event_id,
                    "market_id": market_id,
                    "status": analysis.get("status"),
                    "ai_request_id": analysis.get("ai_request_id"),
                    "confidence": analysis.get("confidence"),
                },
                source_service="news_neuron",
                aggregate_type="news_event",
                aggregate_id=news_event_id,
            )
        except Exception:
            pass

