from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.services.dry_run_provenance import DryRunProvenanceService


class AnalyzeDryRunProvenanceRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)


def create_dry_run_provenance_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    service: DryRunProvenanceService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/provenance/dry-run", tags=["dry-run-provenance"])
    factory = connection_factory or DatabaseConnectionFactory()
    provenance_service = service or DryRunProvenanceService(connection_factory=factory)

    @router.get("/recent")
    async def recent_provenance(
        limit: int = Query(default=50, ge=1, le=500),
        object_type: str | None = None,
        generated_by: str | None = None,
        provenance_status: str | None = None,
    ) -> dict[str, Any]:
        items = provenance_service.list_provenance(
            limit=limit,
            object_type=object_type,
            generated_by=generated_by,
            provenance_status=provenance_status,
        )
        return {"status": "OK", "mock_data": False, "count": len(items), "provenance": items}

    @router.get("/{object_type}/{object_id}")
    async def get_provenance(object_type: str, object_id: str) -> dict[str, Any]:
        item = provenance_service.get_provenance(object_type, object_id)
        return {"status": "OK" if item else "MISSING", "mock_data": False, "object_type": object_type, "object_id": object_id, "provenance": item}

    @router.post("/analyze/recent")
    async def analyze_recent_provenance(payload: AnalyzeDryRunProvenanceRequest) -> dict[str, Any]:
        return provenance_service.analyze_recent(limit=payload.limit)

    return router
