from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.strategy.service import StrategyService


class StrategyRouteRequest(BaseModel):
    market_id: str = Field(min_length=1)
    side: str | None = None
    dry_run: bool = False
    manual_input: dict[str, Any] | None = None
    hunt_approval: bool = False


def create_strategy_router(*, connection_factory: DatabaseConnectionFactory | None = None, service: StrategyService | None = None) -> APIRouter:
    router = APIRouter(prefix="/strategy", tags=["strategy"])
    factory = connection_factory or DatabaseConnectionFactory()
    strategy_service = service or StrategyService(connection_factory=factory)

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return strategy_service.health()

    @router.get("/market/{market_id}")
    async def market(market_id: str) -> dict[str, Any]:
        return strategy_service.latest_for_market(market_id)

    @router.get("/recent")
    async def recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = strategy_service.recent(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/engines")
    async def engines() -> dict[str, Any]:
        rows = strategy_service.engines()
        return {"items": rows, "count": len(rows)}

    @router.get("/rejections/recent")
    async def rejections_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = strategy_service.rejections_recent(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/cooldowns")
    async def cooldowns() -> dict[str, Any]:
        rows = strategy_service.cooldowns_active()
        return {"items": rows, "count": len(rows)}

    @router.get("/run/{run_id}")
    async def run_detail(run_id: str) -> dict[str, Any]:
        return strategy_service.run_detail(run_id)

    @router.post("/route")
    async def route(payload: StrategyRouteRequest) -> dict[str, Any]:
        try:
            return strategy_service.route_market(
                payload.market_id,
                side=payload.side,
                dry_run=payload.dry_run,
                manual_input=payload.manual_input,
                hunt_approval=payload.hunt_approval,
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router

