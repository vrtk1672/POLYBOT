from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.ai_brain.cache import AICache
from app.ai_brain.contracts import AIRequest, AITaskType, normalize_task_type
from app.ai_brain.cost_ledger import AICostLedger
from app.ai_brain.decision_log import AIDecisionLog
from app.ai_brain.model_performance import AIModelPerformanceTracker
from app.ai_brain.service import HybridAIBrainService
from app.db.connection import DatabaseConnectionFactory
from app.repositories.ai_request_repository import AIRequestRepository


class AnalyzeRequest(BaseModel):
    task_type: str
    market_id: str | None = None
    event_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    allow_cloud: bool = False
    reason: str = Field(min_length=1)


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in dict(row).items():
        if hasattr(value, "isoformat"):
            output[key] = value.isoformat()
        else:
            output[key] = value
    return output


def create_ai_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    ai_service: HybridAIBrainService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/ai", tags=["ai-brain"])
    factory = connection_factory or DatabaseConnectionFactory()
    service = ai_service or HybridAIBrainService(connection_factory=factory)
    cache = AICache(connection_factory=factory)
    costs = AICostLedger(connection_factory=factory)
    decisions = AIDecisionLog(connection_factory=factory)
    performance = AIModelPerformanceTracker(connection_factory=factory)
    requests = AIRequestRepository()

    @router.get("/health")
    async def ai_health() -> dict[str, Any]:
        return service.health()

    @router.get("/costs")
    async def ai_costs(model: str | None = None, task_type: str | None = None) -> dict[str, Any]:
        return costs.summarize_costs(model=model, task_type=task_type)

    @router.get("/cache")
    async def ai_cache(
        task_type: str | None = None,
        market_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        entries = [_serialize(row) for row in cache.list_cache(task_type=task_type, market_id=market_id, limit=limit)]
        return {"cache_entries": entries, "hit_rate": cache.hit_rate(), "count": len(entries)}

    @router.get("/escalations")
    async def ai_escalations(status: str | None = None, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        if not factory.enabled:
            return {"escalations": [], "count": 0}
        with factory.connect() as conn:
            rows = requests.list_escalations(conn, status=status, limit=limit)
        return {"escalations": [_serialize(row) for row in rows], "count": len(rows)}

    @router.get("/decisions")
    async def ai_decisions(
        market_id: str | None = None,
        task_type: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        rows = decisions.list_decisions(market_id=market_id, task_type=task_type, limit=limit)
        return {"decisions": [_serialize(row) for row in rows], "count": len(rows)}

    @router.get("/model-performance")
    async def ai_model_performance(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
        rows = [_serialize(row) for row in performance.list_summary(limit=limit)]
        return {"models": rows, "count": len(rows)}

    @router.post("/analyze")
    async def ai_analyze(payload: AnalyzeRequest) -> dict[str, Any]:
        try:
            task = normalize_task_type(payload.task_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not payload.market_id and not payload.input_payload:
            raise HTTPException(status_code=400, detail="market_id or input_payload is required")
        request = AIRequest(
            task_type=task,
            market_id=payload.market_id,
            event_id=payload.event_id,
            input_payload=payload.input_payload,
            metadata={"api_reason": payload.reason},
        )
        response = service.analyze(request, allow_cloud=payload.allow_cloud, reason=payload.reason)
        return {
            "ai_request_id": response.ai_request_id,
            "task_type": response.task_type.value if isinstance(response.task_type, AITaskType) else str(response.task_type),
            "model_name": response.model_name,
            "structured_output": response.structured_output,
            "confidence": response.confidence,
            "risk_flags": response.risk_flags,
            "recommended_action": response.recommended_action,
            "metadata": response.metadata,
        }

    return router
