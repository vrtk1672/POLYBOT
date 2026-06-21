from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.brains.service import BrainService
from app.db.connection import DatabaseConnectionFactory


class ContextAnalyzeRequest(BaseModel):
    market_id: str = Field(min_length=1)
    dry_run: bool = False
    manual_input: dict[str, Any] | None = None


class CapitalAnalyzeRequest(BaseModel):
    market_id: str | None = None
    candidate_engine: str | None = None
    dry_run: bool = False
    manual_input: dict[str, Any] | None = None


class CombinedAnalyzeRequest(BaseModel):
    market_id: str = Field(min_length=1)
    candidate_engine: str | None = None
    dry_run: bool = False
    manual_context: dict[str, Any] | None = None
    manual_capital: dict[str, Any] | None = None


def create_brain_router(*, connection_factory: DatabaseConnectionFactory | None = None, service: BrainService | None = None) -> APIRouter:
    router = APIRouter(prefix="/brains", tags=["brains"])
    factory = connection_factory or DatabaseConnectionFactory()
    brain_service = service or BrainService(connection_factory=factory)

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return brain_service.health()

    @router.get("/context/market/{market_id}")
    async def context_market(market_id: str) -> dict[str, Any]:
        return brain_service.latest_context(market_id)

    @router.get("/capital/market/{market_id}")
    async def capital_market(market_id: str) -> dict[str, Any]:
        return brain_service.latest_capital(market_id)

    @router.get("/market/{market_id}")
    async def market(market_id: str) -> dict[str, Any]:
        return brain_service.combined(market_id)

    @router.get("/context/recent")
    async def context_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = brain_service.recent_context(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/capital/recent")
    async def capital_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = brain_service.recent_capital(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/blocked/recent")
    async def blocked_recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        return brain_service.recent_blocked(limit=limit)

    @router.post("/context/analyze")
    async def context_analyze(payload: ContextAnalyzeRequest) -> dict[str, Any]:
        try:
            return brain_service.analyze_context(payload.market_id, dry_run=payload.dry_run, manual_input=payload.manual_input)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/capital/analyze")
    async def capital_analyze(payload: CapitalAnalyzeRequest) -> dict[str, Any]:
        try:
            return brain_service.analyze_capital(market_id=payload.market_id, candidate_engine=payload.candidate_engine, dry_run=payload.dry_run, manual_input=payload.manual_input)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/analyze")
    async def analyze(payload: CombinedAnalyzeRequest) -> dict[str, Any]:
        try:
            return brain_service.analyze_both(
                payload.market_id,
                candidate_engine=payload.candidate_engine,
                dry_run=payload.dry_run,
                manual_context=payload.manual_context,
                manual_capital=payload.manual_capital,
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
