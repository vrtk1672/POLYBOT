from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.risk.service import RiskService


class RiskGovernorRebuildRequest(BaseModel):
    dry_run: bool = False
    manual_payload: dict[str, Any] | None = None


class RiskGateEvaluateRequest(BaseModel):
    market_id: str = Field(min_length=1)
    strategy_route_id: int | None = None
    allocation_id: str | None = None
    dry_run: bool = False
    manual_input: dict[str, Any] | None = None


class RiskOverrideRequest(BaseModel):
    actor: str | None = None
    reason: str | None = None
    scope: str | None = None
    scope_key: str | None = None
    override_type: str | None = None
    expires_at: str | None = None
    dry_run: bool = False
    governor_status: str | None = None


def create_risk_router(*, connection_factory: DatabaseConnectionFactory | None = None, service: RiskService | None = None) -> APIRouter:
    router = APIRouter(prefix="/risk", tags=["risk"])
    factory = connection_factory or DatabaseConnectionFactory()
    risk_service = service or RiskService(connection_factory=factory)

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return risk_service.health()

    @router.get("/governor")
    async def governor() -> dict[str, Any]:
        return risk_service.governor_latest()

    @router.get("/limits")
    async def limits() -> dict[str, Any]:
        rows = risk_service.limits_list()
        return {"items": rows, "count": len(rows)}

    @router.get("/breaches/recent")
    async def breaches_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = risk_service.breaches_recent(limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/cooldowns")
    async def cooldowns() -> dict[str, Any]:
        rows = risk_service.cooldowns_active()
        return {"items": rows, "count": len(rows)}

    @router.get("/gate/recent")
    async def gate_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = risk_service.gate_recent(limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/gate/{run_id}")
    async def gate_detail(run_id: str) -> dict[str, Any]:
        return risk_service.gate_detail(run_id)

    @router.post("/governor/rebuild")
    async def rebuild(payload: RiskGovernorRebuildRequest) -> dict[str, Any]:
        try:
            return risk_service.rebuild_governor(dry_run=payload.dry_run, manual_payload=payload.manual_payload)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/gate/evaluate")
    async def evaluate(payload: RiskGateEvaluateRequest) -> dict[str, Any]:
        try:
            return risk_service.evaluate_gate(
                market_id=payload.market_id,
                strategy_route_id=payload.strategy_route_id,
                allocation_id=payload.allocation_id,
                dry_run=payload.dry_run,
                manual_input=payload.manual_input,
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/override")
    async def override(payload: RiskOverrideRequest) -> dict[str, Any]:
        try:
            body = payload.model_dump(exclude={"dry_run"})
            return risk_service.create_override(payload=body, dry_run=payload.dry_run)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router

