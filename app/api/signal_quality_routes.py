from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.services.signal_quality import SignalQualityService


class EvaluateRecentSignalsRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)


def create_signal_quality_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    service: SignalQualityService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/signals", tags=["signal-quality"])
    factory = connection_factory or DatabaseConnectionFactory()
    quality_service = service or SignalQualityService(connection_factory=factory)

    @router.get("/quality/recent")
    async def recent_signal_quality(
        limit: int = Query(default=50, ge=1, le=500),
        quality_status: str | None = None,
        can_feed_brain: bool | None = None,
        can_feed_paper: bool | None = None,
    ) -> dict[str, Any]:
        items = quality_service.list_signal_quality(
            limit=limit,
            quality_status=quality_status,
            can_feed_brain=can_feed_brain,
            can_feed_paper=can_feed_paper,
        )
        return {"status": "OK", "mock_data": False, "count": len(items), "quality": items}

    @router.post("/quality/evaluate/recent")
    async def evaluate_recent_signal_quality(payload: EvaluateRecentSignalsRequest) -> dict[str, Any]:
        return quality_service.evaluate_recent_signals(limit=payload.limit)

    @router.post("/{signal_id}/quality/evaluate")
    async def evaluate_one_signal_quality(signal_id: str) -> dict[str, Any]:
        item = quality_service.evaluate_signal_quality(signal_id)
        return {"status": "OK" if item else "MISSING", "mock_data": False, "signal_id": signal_id, "quality": item}

    @router.get("/{signal_id}/quality")
    async def get_signal_quality(signal_id: str) -> dict[str, Any]:
        item = quality_service.get_signal_quality(signal_id)
        return {"status": "OK" if item else "MISSING", "mock_data": False, "signal_id": signal_id, "quality": item}

    return router
