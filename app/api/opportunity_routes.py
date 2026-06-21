from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.opportunity.service import OpportunityService


class OpportunityScoreRequest(BaseModel):
    market_id: str = Field(min_length=1)
    side: str | None = None
    dry_run: bool = False
    manual_input: dict[str, Any] | None = None


def create_opportunity_router(*, connection_factory: DatabaseConnectionFactory | None = None, service: OpportunityService | None = None) -> APIRouter:
    router = APIRouter(prefix="/opportunities", tags=["opportunities"])
    factory = connection_factory or DatabaseConnectionFactory()
    opportunity_service = service or OpportunityService(connection_factory=factory)

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return opportunity_service.health()

    @router.get("/market/{market_id}")
    async def market(market_id: str) -> dict[str, Any]:
        return opportunity_service.latest_for_market(market_id)

    @router.get("/recent")
    async def recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = opportunity_service.recent(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/top")
    async def top(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        rows = opportunity_service.top(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/blocked/recent")
    async def blocked_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = opportunity_service.blocked_recent(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/risk-flags/recent")
    async def risk_flags_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = opportunity_service.risk_flags_recent(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/run/{run_id}")
    async def run_detail(run_id: str) -> dict[str, Any]:
        return opportunity_service.run_detail(run_id)

    @router.post("/score")
    async def score(payload: OpportunityScoreRequest) -> dict[str, Any]:
        try:
            return opportunity_service.score_market(payload.market_id, side=payload.side, dry_run=payload.dry_run, manual_input=payload.manual_input)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router

