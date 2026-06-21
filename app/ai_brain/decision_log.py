from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.ai_brain.contracts import AIDecision, AIRequest, AIResponse
from app.db.connection import DatabaseConnectionFactory
from app.repositories.ai_decision_repository import AIDecisionRepository


class AIDecisionLog:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, repository: AIDecisionRepository | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or AIDecisionRepository()

    def log_decision(
        self,
        *,
        request: AIRequest,
        response: AIResponse,
        ai_request_id: str | None = None,
        decision_type: str = "INTERPRETATION",
        cannot_trade_reason: str | None = "AI interpretation only; trading requires State Governor and Risk Gate",
    ) -> str:
        decision = AIDecision(
            decision_type=decision_type,
            task_type=request.task_type,
            market_id=request.market_id,
            confidence=response.confidence,
            output_json=response.structured_output,
            risk_flags=response.risk_flags,
            cannot_trade_reason=cannot_trade_reason,
            metadata={"source": "v2.3_ai_brain"},
        )
        decision_id = f"ai_dec_{uuid4().hex}"
        if self._factory.enabled:
            try:
                with self._factory.connect() as conn:
                    self._repository.insert_decision(
                        conn,
                        ai_decision_id=decision_id,
                        ai_request_id=ai_request_id,
                        market_id=request.market_id,
                        event_id=request.event_id,
                        correlation_id=request.correlation_id,
                        task_type=request.task_type.value,
                        decision_type=decision.decision_type,
                        output_json=decision.output_json,
                        confidence=decision.confidence,
                        risk_flags=decision.risk_flags,
                        cannot_trade_reason=decision.cannot_trade_reason,
                        metadata=decision.metadata,
                    )
                    conn.commit()
            except Exception:
                return decision_id
        return decision_id

    def list_decisions(self, *, market_id: str | None = None, task_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        try:
            with self._factory.connect() as conn:
                return [dict(row) for row in self._repository.list_decisions(conn, market_id=market_id, task_type=task_type, limit=limit)]
        except Exception:
            return []
