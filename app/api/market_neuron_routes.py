from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.market_neuron.service import MarketNeuronService


class MarketAnalyzeRequest(BaseModel):
    market_id: str = Field(min_length=1)
    token_id: str | None = None
    side: str = "UNKNOWN"
    raw_market_snapshot: dict[str, Any] | None = None
    raw_orderbook: dict[str, Any] | None = None
    reason: str = Field(min_length=1)


def create_market_neuron_router(*, connection_factory: DatabaseConnectionFactory | None = None, service: MarketNeuronService | None = None) -> APIRouter:
    router = APIRouter(prefix="/market-neuron", tags=["market-neuron"])
    factory = connection_factory or DatabaseConnectionFactory()
    market_service = service or MarketNeuronService(connection_factory=factory)

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return market_service.health()

    @router.get("/market/{market_id}")
    async def market_truth(market_id: str) -> dict[str, Any]:
        return market_service.latest_market_truth(market_id)

    @router.get("/signals/recent")
    async def recent_signals(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = market_service.recent_signals(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/blocked/recent")
    async def recent_blocked(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        rows = market_service.recent_blocked(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.get("/top")
    async def top_markets(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        rows = market_service.top_markets(limit=limit)
        return {"items": rows, "count": len(rows)}

    @router.post("/analyze")
    async def analyze(payload: MarketAnalyzeRequest) -> dict[str, Any]:
        try:
            return market_service.analyze_market(
                payload.market_id,
                token_id=payload.token_id,
                side=payload.side,
                raw_market_snapshot=payload.raw_market_snapshot,
                raw_orderbook=payload.raw_orderbook,
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router

