from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.services.mesh_dry_run import MeshDryRunService


class FirstIntelligenceDryRunRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    market_id: str | None = None
    dry_run_only: bool = True


def create_mesh_dry_run_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    service: MeshDryRunService | None = None,
) -> APIRouter:
    router = APIRouter(tags=["mesh-dry-run"])
    factory = connection_factory or DatabaseConnectionFactory()
    dry_run_service = service or MeshDryRunService(connection_factory=factory)

    @router.get("/mesh/dry-runs/recent")
    async def recent_dry_runs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
        dry_runs = dry_run_service.get_latest_dry_runs(limit=limit)
        return {"status": "OK", "mock_data": False, "count": len(dry_runs), "dry_runs": dry_runs}

    @router.get("/mesh/dry-runs/{dry_run_id}")
    async def get_dry_run(dry_run_id: str) -> dict[str, Any]:
        item = dry_run_service.get_dry_run(dry_run_id)
        return {"status": "OK" if item else "MISSING", "mock_data": False, "dry_run_id": dry_run_id, "dry_run": item}

    @router.post("/mesh/dry-run/first-intelligence")
    async def first_intelligence_dry_run(payload: FirstIntelligenceDryRunRequest) -> dict[str, Any]:
        return dry_run_service.run_first_intelligence_dry_run(
            limit=payload.limit,
            market_id=payload.market_id,
            dry_run_only=payload.dry_run_only,
        )

    return router
