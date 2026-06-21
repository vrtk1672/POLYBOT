from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.connection import DatabaseConnectionFactory
from app.market_memory.service import MarketMemoryService


class MarketMemoryRebuildRequest(BaseModel):
    market_id: str | None = None
    market_family: str | None = None
    dry_run: bool = False


def create_market_memory_router(*, connection_factory: DatabaseConnectionFactory | None = None, service: MarketMemoryService | None = None) -> APIRouter:
    router = APIRouter(prefix="/market-memory", tags=["market-memory"])
    factory = connection_factory or DatabaseConnectionFactory()
    memory_service = service or MarketMemoryService(connection_factory=factory)

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return memory_service.health()

    @router.get("/market/{market_id}")
    async def market(market_id: str) -> dict[str, Any]:
        return memory_service.market(market_id)

    @router.get("/family/{market_family}")
    async def family(market_family: str) -> dict[str, Any]:
        return memory_service.family(market_family)

    @router.get("/engines")
    async def engines(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = memory_service.list_table("engine_performance_memory", limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/sources")
    async def sources(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = memory_service.list_table("source_reliability_memory", limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/whales")
    async def whales(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = memory_service.list_table("whale_memory", limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/slippage")
    async def slippage(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = memory_service.list_table("slippage_memory", limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/rules-risk")
    async def rules_risk(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = memory_service.list_table("rules_risk_memory", limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/no-trade")
    async def no_trade(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = memory_service.list_table("no_trade_memory", limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/recent")
    async def recent(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = memory_service.list_table("market_memory_v2", limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.post("/rebuild")
    async def rebuild(payload: MarketMemoryRebuildRequest) -> dict[str, Any]:
        try:
            return memory_service.rebuild(
                market_id=payload.market_id,
                market_family=payload.market_family,
                dry_run=payload.dry_run,
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
