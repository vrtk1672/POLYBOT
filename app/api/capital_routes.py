from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.capital.service import CapitalService
from app.db.connection import DatabaseConnectionFactory


class CapitalStateRebuildRequest(BaseModel):
    dry_run: bool = False
    manual_capital: dict[str, Any] | None = None


class CapitalAllocateRequest(BaseModel):
    market_id: str = Field(min_length=1)
    strategy_route_id: int | None = None
    requested_size_usd: float | None = None
    dry_run: bool = False
    manual_route: dict[str, Any] | None = None
    manual_capital: dict[str, Any] | None = None


class ReinvestEvaluateRequest(BaseModel):
    dry_run: bool = False
    realized_profit_usd: float | None = None


def create_capital_router(*, connection_factory: DatabaseConnectionFactory | None = None, service: CapitalService | None = None) -> APIRouter:
    router = APIRouter(prefix="/capital", tags=["capital"])
    factory = connection_factory or DatabaseConnectionFactory()
    capital_service = service or CapitalService(connection_factory=factory)

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return capital_service.health()

    @router.get("/state")
    async def state() -> dict[str, Any]:
        return capital_service.latest_state()

    @router.get("/budgets")
    async def budgets() -> dict[str, Any]:
        rows = capital_service.budgets()
        return {"items": rows, "count": len(rows)}

    @router.get("/allocations/recent")
    async def allocations_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = capital_service.allocations_recent(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/events/recent")
    async def events_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = capital_service.events_recent(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/reinvest")
    async def reinvest() -> dict[str, Any]:
        return capital_service.reinvest_summary()

    @router.post("/state/rebuild")
    async def rebuild(payload: CapitalStateRebuildRequest) -> dict[str, Any]:
        try:
            return capital_service.rebuild_state(dry_run=payload.dry_run, manual_payload=payload.manual_capital)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/allocate")
    async def allocate(payload: CapitalAllocateRequest) -> dict[str, Any]:
        try:
            return capital_service.allocate(
                market_id=payload.market_id,
                strategy_route_id=payload.strategy_route_id,
                requested_size_usd=payload.requested_size_usd,
                dry_run=payload.dry_run,
                manual_route=payload.manual_route,
                manual_capital=payload.manual_capital,
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/reinvest/evaluate")
    async def reinvest_evaluate(payload: ReinvestEvaluateRequest) -> dict[str, Any]:
        try:
            return capital_service.evaluate_reinvest(dry_run=payload.dry_run, realized_profit_usd=payload.realized_profit_usd)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router

