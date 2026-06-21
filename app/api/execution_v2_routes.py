from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.execution_v2.service import ExecutionV2Service


class ExecutionRequest(BaseModel):
    market_id: str = Field(min_length=1)
    strategy_route_id: int | None = None
    allocation_id: str | None = None
    risk_decision_id: int | None = None
    exit_plan_id: str | None = None
    execution_mode: str = "PAPER_SIM"
    dry_run: bool = False
    manual_input: dict[str, Any] | None = None


class CancelEvaluateRequest(BaseModel):
    order_id: str = Field(min_length=1)
    current: dict[str, Any] | None = None
    dry_run: bool = False


def create_execution_v2_router(*, connection_factory: DatabaseConnectionFactory | None = None, service: ExecutionV2Service | None = None) -> APIRouter:
    router = APIRouter(prefix="/execution", tags=["execution"])
    factory = connection_factory or DatabaseConnectionFactory()
    execution_service = service or ExecutionV2Service(connection_factory=factory)

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return execution_service.health()

    @router.get("/orders/recent")
    async def orders_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = execution_service.orders_recent(limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/orders/{order_id}")
    async def order_detail(order_id: str) -> dict[str, Any]:
        return execution_service.order_detail(order_id)

    @router.get("/fills/recent")
    async def fills_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = execution_service.fills_recent(limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/errors/recent")
    async def errors_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = execution_service.errors_recent(limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/quality/recent")
    async def quality_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = execution_service.quality_recent(limit)
        return {"items": rows, "count": len(rows)}

    @router.post("/precheck")
    async def precheck(payload: ExecutionRequest) -> dict[str, Any]:
        try:
            return execution_service.precheck(market_id=payload.market_id, execution_mode=payload.execution_mode, strategy_route_id=payload.strategy_route_id, allocation_id=payload.allocation_id, risk_decision_id=payload.risk_decision_id, exit_plan_id=payload.exit_plan_id, manual_input=payload.manual_input)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/paper/simulate")
    async def paper_simulate(payload: ExecutionRequest) -> dict[str, Any]:
        try:
            return execution_service.paper_simulate(market_id=payload.market_id, strategy_route_id=payload.strategy_route_id, allocation_id=payload.allocation_id, risk_decision_id=payload.risk_decision_id, exit_plan_id=payload.exit_plan_id, dry_run=payload.dry_run, manual_input=payload.manual_input)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/shadow/plan")
    async def shadow_plan(payload: ExecutionRequest) -> dict[str, Any]:
        try:
            return execution_service.shadow_plan(market_id=payload.market_id, strategy_route_id=payload.strategy_route_id, allocation_id=payload.allocation_id, risk_decision_id=payload.risk_decision_id, exit_plan_id=payload.exit_plan_id, dry_run=payload.dry_run, manual_input=payload.manual_input)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/cancel-evaluate")
    async def cancel_evaluate(payload: CancelEvaluateRequest) -> dict[str, Any]:
        try:
            return execution_service.cancel_evaluate(order_id=payload.order_id, current=payload.current, dry_run=payload.dry_run)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router

