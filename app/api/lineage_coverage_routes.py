from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.services.lineage_coverage import LineageCoverageService


class AnalyzeLineageCoverageRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)


def create_lineage_coverage_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    service: LineageCoverageService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/signals", tags=["lineage-coverage"])
    factory = connection_factory or DatabaseConnectionFactory()
    coverage_service = service or LineageCoverageService(connection_factory=factory)

    @router.get("/lineage-coverage/recent")
    async def recent_lineage_coverage(
        limit: int = Query(default=50, ge=1, le=500),
        lineage_status: str | None = None,
        reason: str | None = None,
        producer: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        items = coverage_service.list_lineage_coverage(
            limit=limit,
            lineage_status=lineage_status,
            reason=reason,
            producer=producer,
            source=source,
        )
        return {"status": "OK", "mock_data": False, "count": len(items), "lineage_coverage": items}

    @router.post("/lineage-coverage/analyze/recent")
    async def analyze_recent_lineage_coverage(payload: AnalyzeLineageCoverageRequest) -> dict[str, Any]:
        return coverage_service.analyze_recent_signals(limit=payload.limit)

    @router.get("/{signal_id}/lineage-coverage")
    async def get_signal_lineage_coverage(signal_id: str) -> dict[str, Any]:
        item = coverage_service.get_lineage_coverage(signal_id)
        return {"status": "OK" if item else "MISSING", "mock_data": False, "signal_id": signal_id, "lineage_coverage": item}

    @router.post("/{signal_id}/lineage-coverage/analyze")
    async def analyze_signal_lineage_coverage(signal_id: str) -> dict[str, Any]:
        item = coverage_service.analyze_signal(signal_id)
        return {"status": "OK" if item else "MISSING", "mock_data": False, "signal_id": signal_id, "lineage_coverage": item}

    return router
