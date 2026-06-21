from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_outputs import BrainOutputService


def create_brain_output_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    service: BrainOutputService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/brain-outputs", tags=["brain-outputs"])
    factory = connection_factory or DatabaseConnectionFactory()
    brain_output_service = service or BrainOutputService(connection_factory=factory)

    @router.get("/recent")
    async def recent_outputs(
        limit: int = Query(default=50, ge=1, le=500),
        brain: str | None = None,
        market_id: str | None = None,
        position_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        outputs = brain_output_service.list_recent_brain_outputs(
            limit=limit,
            brain=brain,
            market_id=market_id,
            position_id=position_id,
            status=status,
        )
        return {"status": "OK", "mock_data": False, "count": len(outputs), "outputs": outputs}

    @router.get("/conflicts/recent")
    async def recent_conflicts(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        conflicts = brain_output_service.list_conflicts(limit=limit)
        return {"status": "OK", "mock_data": False, "count": len(conflicts), "conflicts": conflicts}

    @router.get("/market/{market_id}")
    async def market_outputs(market_id: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        outputs = brain_output_service.list_outputs_by_market(market_id, limit=limit)
        return {"status": "OK", "mock_data": False, "market_id": market_id, "count": len(outputs), "outputs": outputs}

    @router.get("/brain/{brain_name}")
    async def brain_outputs(brain_name: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        outputs = brain_output_service.list_outputs_by_brain(brain_name, limit=limit)
        return {"status": "OK", "mock_data": False, "brain": brain_name, "count": len(outputs), "outputs": outputs}

    @router.get("/signal/{signal_id}")
    async def signal_outputs(signal_id: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        outputs = brain_output_service.list_outputs_by_signal_dependency(signal_id, limit=limit)
        return {"status": "OK", "mock_data": False, "signal_id": signal_id, "count": len(outputs), "outputs": outputs}

    @router.get("/{brain_output_id}")
    async def get_output(brain_output_id: str) -> dict[str, Any]:
        item = brain_output_service.get_brain_output(brain_output_id)
        return {
            "status": "OK" if item else "MISSING",
            "mock_data": False,
            "brain_output_id": brain_output_id,
            "output": item,
        }

    return router
