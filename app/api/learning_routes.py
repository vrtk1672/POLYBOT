from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.learning.service import LearningService


class TradeReviewRequest(BaseModel):
    order_id: str | None = None
    trade_id: str | None = None
    dry_run: bool = False
    manual_completed_trade: dict[str, Any] | None = None


class NoTradeReviewRequest(BaseModel):
    no_trade_id: str = Field(min_length=1)
    dry_run: bool = False


class LearningRebuildRequest(BaseModel):
    dry_run: bool = False
    scope: str | None = None
    market_id: str | None = None


def create_learning_router(service: LearningService | None = None) -> APIRouter:
    router = APIRouter(prefix="/learning", tags=["learning"])
    svc = service or LearningService(connection_factory=DatabaseConnectionFactory())

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return svc.health()

    @router.get("/trade-reviews/recent")
    async def trade_reviews_recent(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        return {"items": svc.recent_trade_reviews(limit=limit)}

    @router.get("/signals")
    async def signals() -> dict[str, Any]:
        return svc.signals()

    @router.get("/engines")
    async def engines() -> dict[str, Any]:
        return svc.engines()

    @router.get("/sources")
    async def sources() -> dict[str, Any]:
        return svc.sources()

    @router.get("/whales")
    async def whales() -> dict[str, Any]:
        return svc.whales()

    @router.get("/ai")
    async def ai() -> dict[str, Any]:
        return svc.ai()

    @router.get("/no-trade")
    async def no_trade() -> dict[str, Any]:
        return svc.no_trade()

    @router.get("/model-adjustments")
    async def model_adjustments() -> dict[str, Any]:
        return svc.model_adjustments()

    @router.get("/snapshot")
    async def snapshot() -> dict[str, Any]:
        return svc.snapshot()

    @router.post("/review/trade")
    async def review_trade(request: TradeReviewRequest) -> dict[str, Any]:
        payload = dict(request.manual_completed_trade or {})
        if request.order_id is not None:
            payload.setdefault("order_id", request.order_id)
        if request.trade_id is not None:
            payload.setdefault("trade_id", request.trade_id)
        return svc.review_trade(payload, dry_run=request.dry_run)

    @router.post("/review/no-trade")
    async def review_no_trade(request: NoTradeReviewRequest) -> dict[str, Any]:
        return svc.review_no_trade(request.no_trade_id, dry_run=request.dry_run)

    @router.post("/rebuild")
    async def rebuild(request: LearningRebuildRequest) -> dict[str, Any]:
        return svc.rebuild(dry_run=request.dry_run, scope=request.scope, market_id=request.market_id)

    return router
