from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.services.signal_processing import SignalProcessingService


class EvaluateProcessingRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    refresh_quality: bool = False


class EvaluateOneProcessingRequest(BaseModel):
    refresh_quality: bool = False


def create_signal_processing_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    service: SignalProcessingService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/signals", tags=["signal-processing"])
    factory = connection_factory or DatabaseConnectionFactory()
    processing_service = service or SignalProcessingService(connection_factory=factory)

    @router.get("/processing/recent")
    async def recent_processing_states(
        limit: int = Query(default=50, ge=1, le=500),
        state: str | None = None,
        gate_status: str | None = None,
        include_quality: bool = False,
    ) -> dict[str, Any]:
        items = processing_service.list_signal_processing(limit=limit, state=state, gate_status=gate_status)
        if not include_quality:
            for item in items:
                item.pop("quality_evaluation_id", None)
        return {"status": "OK", "mock_data": False, "count": len(items), "processing": items}

    @router.post("/processing/evaluate/recent")
    async def evaluate_recent_processing(payload: EvaluateProcessingRequest) -> dict[str, Any]:
        return processing_service.evaluate_recent_signals(limit=payload.limit, refresh_quality=payload.refresh_quality)

    @router.post("/{signal_id}/processing/evaluate")
    async def evaluate_signal_processing(signal_id: str, payload: EvaluateOneProcessingRequest) -> dict[str, Any]:
        item = processing_service.evaluate_signal_processing(signal_id, refresh_quality=payload.refresh_quality)
        return {"status": "OK" if item else "MISSING", "mock_data": False, "signal_id": signal_id, "processing": item}

    @router.get("/{signal_id}/processing")
    async def get_signal_processing(signal_id: str) -> dict[str, Any]:
        item = processing_service.get_signal_processing(signal_id)
        return {"status": "OK" if item else "MISSING", "mock_data": False, "signal_id": signal_id, "processing": item}

    return router
