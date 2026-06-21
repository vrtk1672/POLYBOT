from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.exit_cortex.service import ExitCortexService


class ExitPlanRequest(BaseModel):
    market_id: str = Field(min_length=1)
    order_id: str | None = None
    strategy_route_id: int | None = None
    allocation_id: str | None = None
    risk_decision_id: int | None = None
    execution_order_id: str | None = None
    dry_run: bool = False
    manual_input: dict[str, Any] | None = None


class ExitEvaluateRequest(BaseModel):
    exit_plan_id: str = Field(min_length=1)
    dry_run: bool = False
    current: dict[str, Any] | None = None


class ExitEmergencyRequest(BaseModel):
    exit_plan_id: str | None = None
    order_id: str | None = None
    reason: str = Field(min_length=1)
    dry_run: bool = False
    current: dict[str, Any] | None = None


def create_exit_router(service: ExitCortexService | None = None) -> APIRouter:
    router = APIRouter(prefix="/exits", tags=["exits"])
    svc = service or ExitCortexService(connection_factory=DatabaseConnectionFactory())

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return svc.health()

    @router.get("/plans/recent")
    async def plans_recent(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        return {"items": svc.recent_plans(limit=limit)}

    @router.get("/plans/{exit_plan_id}")
    async def plan_detail(exit_plan_id: str) -> dict[str, Any]:
        try:
            return svc.plan_detail(exit_plan_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/intents/recent")
    async def intents_recent(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        return {"items": svc.recent_intents(limit=limit)}

    @router.get("/events/recent")
    async def events_recent(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        return {"items": svc.recent_events(limit=limit)}

    @router.get("/failures/recent")
    async def failures_recent(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        return {"items": svc.recent_failures(limit=limit)}

    @router.get("/quality/recent")
    async def quality_recent(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        return {"items": svc.recent_quality(limit=limit)}

    @router.get("/orphans")
    async def orphans(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        return {"items": svc.orphan_orders(limit=limit)}

    @router.post("/plan")
    async def create_plan(request: ExitPlanRequest) -> dict[str, Any]:
        return svc.create_plan(
            market_id=request.market_id,
            order_id=request.order_id,
            strategy_route_id=request.strategy_route_id,
            allocation_id=request.allocation_id,
            risk_decision_id=request.risk_decision_id,
            execution_order_id=request.execution_order_id,
            dry_run=request.dry_run,
            manual_input=request.manual_input,
        )

    @router.post("/evaluate")
    async def evaluate(request: ExitEvaluateRequest) -> dict[str, Any]:
        try:
            return svc.evaluate(exit_plan_id=request.exit_plan_id, dry_run=request.dry_run, current=request.current)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/emergency")
    async def emergency(request: ExitEmergencyRequest) -> dict[str, Any]:
        try:
            return svc.emergency(exit_plan_id=request.exit_plan_id, order_id=request.order_id, reason=request.reason, dry_run=request.dry_run, current=request.current)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
