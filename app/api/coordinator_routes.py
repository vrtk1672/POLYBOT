from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_coordinator import BrainCoordinatorService


class CoordinateOutputsRequest(BaseModel):
    brain_output_ids: list[str] = Field(default_factory=list)
    market_id: str | None = None
    position_id: str | None = None


def create_coordinator_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    service: BrainCoordinatorService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/coordinator", tags=["coordinator"])
    factory = connection_factory or DatabaseConnectionFactory()
    coordinator = service or BrainCoordinatorService(connection_factory=factory)

    @router.get("/decisions/recent")
    async def recent_decisions(
        limit: int = Query(default=50, ge=1, le=500),
        market_id: str | None = None,
        position_id: str | None = None,
        final_state: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        decisions = coordinator.list_recent_decisions(
            limit=limit,
            market_id=market_id,
            position_id=position_id,
            final_state=final_state,
            status=status,
        )
        return {"status": "OK", "mock_data": False, "count": len(decisions), "decisions": decisions}

    @router.get("/decisions/{coordinator_decision_id}")
    async def get_decision(coordinator_decision_id: str) -> dict[str, Any]:
        item = coordinator.get_decision(coordinator_decision_id)
        return {
            "status": "OK" if item else "MISSING",
            "mock_data": False,
            "coordinator_decision_id": coordinator_decision_id,
            "decision": item,
        }

    @router.get("/market/{market_id}")
    async def market_decisions(market_id: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        decisions = coordinator.list_decisions_by_market(market_id, limit=limit)
        return {"status": "OK", "mock_data": False, "market_id": market_id, "count": len(decisions), "decisions": decisions}

    @router.get("/position/{position_id}")
    async def position_decisions(position_id: str, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        decisions = coordinator.list_decisions_by_position(position_id, limit=limit)
        return {"status": "OK", "mock_data": False, "position_id": position_id, "count": len(decisions), "decisions": decisions}

    @router.get("/conflicts/recent")
    async def recent_conflicts(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        conflicts = coordinator.list_conflicts(limit=limit)
        return {"status": "OK", "mock_data": False, "count": len(conflicts), "conflicts": conflicts}

    @router.post("/coordinate/market/{market_id}")
    async def coordinate_market(market_id: str) -> dict[str, Any]:
        decision = coordinator.coordinate_market_outputs(market_id)
        return {"status": "OK", "mock_data": False, "decision": decision}

    @router.post("/coordinate/position/{position_id}")
    async def coordinate_position(position_id: str) -> dict[str, Any]:
        decision = coordinator.coordinate_position_outputs(position_id)
        return {"status": "OK", "mock_data": False, "decision": decision}

    @router.post("/coordinate/outputs")
    async def coordinate_outputs(payload: CoordinateOutputsRequest) -> dict[str, Any]:
        decision = coordinator.coordinate_outputs(
            payload.brain_output_ids,
            market_id=payload.market_id,
            position_id=payload.position_id,
        )
        return {"status": "OK", "mock_data": False, "decision": decision}

    return router
