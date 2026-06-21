from __future__ import annotations

from typing import Any

from app.ai_brain.contracts import AIRequest, AITaskType
from app.ai_brain.service import HybridAIBrainService
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.rules_ai_analysis_repository import RulesAIAnalysisRepository
from app.rules_neuron.contracts import RulesAnalysisResult, RulesRecommendation, RulesInput


class AIWordingAnalyzer:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None, ai_service: HybridAIBrainService | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._ai_service = ai_service or HybridAIBrainService(connection_factory=self._factory, event_bus=self._event_bus)
        self._repo = RulesAIAnalysisRepository()

    def analyze_wording_with_ai(self, rules_input: RulesInput, deterministic_analysis: RulesAnalysisResult, *, allow_cloud: bool = False) -> dict[str, Any]:
        if deterministic_analysis.recommendation == RulesRecommendation.NO_TRADE and deterministic_analysis.wording_risk >= 0.85:
            return {"status": "SKIPPED", "reason": "deterministic_block_sufficient"}
        request = AIRequest(
            task_type=AITaskType.WORDING_RISK_PRECHECK,
            market_id=rules_input.market_id,
            input_payload={
                "question": rules_input.question,
                "rules_text": rules_input.rules_text,
                "deterministic": deterministic_analysis.signal(),
                "instruction": "identify wording risk only; do not create trade decisions",
            },
            metadata={"source": "rules_neuron"},
        )
        try:
            response = self._ai_service.analyze(request, allow_cloud=allow_cloud, reason="rules wording analysis")
            analysis = {"status": "COMPLETED", "ai_request_id": response.ai_request_id, "structured_output": response.structured_output, "confidence": response.confidence, "risk_flags": response.risk_flags}
        except Exception as exc:
            analysis = {"status": "UNAVAILABLE", "reason": str(exc), "confidence": 0.0, "risk_flags": ["ai_unavailable"]}
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                row = self._repo.insert_analysis(
                    conn,
                    market_id=rules_input.market_id,
                    rules_analysis_id=deterministic_analysis.rules_analysis_id,
                    ai_request_id=analysis.get("ai_request_id"),
                    task_type=AITaskType.WORDING_RISK_PRECHECK.value,
                    analysis=analysis,
                    confidence=float(analysis.get("confidence") or 0),
                    risk_flags=list(analysis.get("risk_flags") or []),
                )
            analysis["rules_ai_analysis_id"] = row["rules_ai_analysis_id"]
        self._publish(rules_input.market_id, deterministic_analysis.rules_analysis_id, analysis)
        return analysis

    def _publish(self, market_id: str, rules_analysis_id: str, analysis: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(
                EventType.RULES_AI_ANALYZED.value,
                {"market_id": market_id, "rules_analysis_id": rules_analysis_id, "status": analysis.get("status"), "ai_request_id": analysis.get("ai_request_id")},
                source_service="rules_neuron",
                aggregate_type="market",
                aggregate_id=market_id,
                metadata={"non_trading_event": True},
            )
        except Exception:
            pass

