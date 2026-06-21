from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.no_trade.no_trade_errors import NoTradeValidationError
from app.no_trade.service import NoTradeService
from app.services.paper_intents import PaperIntentGateService


class NoTradeLogRequest(BaseModel):
    market_id: str = Field(min_length=1)
    source_layer: str = Field(min_length=1)
    primary_reason: str | None = None
    reasons: list[str] | None = None
    candidate_engine: str | None = None
    source_run_id: str | None = None
    dry_run: bool = False
    manual_input: dict[str, Any] | None = None


class NoTradeReviewRequest(BaseModel):
    no_trade_id: str = Field(min_length=1)
    dry_run: bool = False
    review_horizon_seconds: int | None = None
    manual_post_fact_payload: dict[str, Any] | None = None


class NoTradeRebuildRequest(BaseModel):
    dry_run: bool = False
    source_layer: str | None = None
    market_id: str | None = None


def create_no_trade_router(service: NoTradeService | None = None) -> APIRouter:
    router = APIRouter(prefix="/no-trade", tags=["no-trade"])
    svc = service or NoTradeService(connection_factory=DatabaseConnectionFactory())

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return svc.health()

    @router.get("/recent")
    async def recent(
        limit: int = Query(default=50, ge=1, le=500),
        category: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, Any]:
        payload = PaperIntentGateService(connection_factory=DatabaseConnectionFactory()).list_no_trade_recent(
            limit=limit,
            category=category,
            market_id=market_id,
        )
        payload["items"] = payload.get("no_trade_records", [])
        return payload

    @router.get("/reasons/top")
    async def reasons_top(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
        return {"items": svc.top_reasons(limit=limit)}

    @router.get("/by-engine")
    async def by_engine() -> dict[str, Any]:
        return {"items": svc.by_engine()}

    @router.get("/by-market-family")
    async def by_market_family() -> dict[str, Any]:
        return {"items": svc.by_market_family()}

    @router.get("/regret")
    async def regret() -> dict[str, Any]:
        return {"summary": svc.regret_summary()}

    @router.get("/reviews/pending")
    async def pending_reviews(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        return {"items": svc.pending_reviews(limit=limit)}

    @router.get("/{no_trade_id}")
    async def detail(no_trade_id: str) -> dict[str, Any]:
        try:
            return svc.detail(no_trade_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/log")
    async def log(request: NoTradeLogRequest) -> dict[str, Any]:
        payload = dict(request.manual_input or {})
        for key, value in request.model_dump(exclude={"manual_input", "dry_run"}).items():
            if value is not None:
                payload[key] = value
        try:
            return svc.log_decision(payload, dry_run=request.dry_run)
        except NoTradeValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/review")
    async def review(request: NoTradeReviewRequest) -> dict[str, Any]:
        try:
            return svc.review(
                no_trade_id=request.no_trade_id,
                dry_run=request.dry_run,
                review_horizon_seconds=request.review_horizon_seconds or 0,
                evidence=request.manual_post_fact_payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/rebuild")
    async def rebuild(request: NoTradeRebuildRequest) -> dict[str, Any]:
        return svc.rebuild(dry_run=request.dry_run, source_layer=request.source_layer, market_id=request.market_id)

    return router
