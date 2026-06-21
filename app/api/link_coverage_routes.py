from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.services.link_coverage import LinkCoverageService


class AnalyzeLinkCoverageRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    create_suggestions: bool = True
    apply_safe_links: bool = False


class AnalyzeOneLinkCoverageRequest(BaseModel):
    create_suggestions: bool = True
    apply_safe_links: bool = False


def create_link_coverage_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    service: LinkCoverageService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/signals", tags=["link-coverage"])
    factory = connection_factory or DatabaseConnectionFactory()
    coverage_service = service or LinkCoverageService(connection_factory=factory)

    @router.get("/link-coverage/recent")
    async def recent_link_coverage(
        limit: int = Query(default=50, ge=1, le=500),
        linkability_status: str | None = None,
        reason: str | None = None,
        include_suggestions: bool = False,
    ) -> dict[str, Any]:
        items = coverage_service.list_link_coverage(
            limit=limit,
            linkability_status=linkability_status,
            reason=reason,
            include_suggestions=include_suggestions,
        )
        return {"status": "OK", "mock_data": False, "count": len(items), "link_coverage": items}

    @router.post("/link-coverage/analyze/recent")
    async def analyze_recent_link_coverage(payload: AnalyzeLinkCoverageRequest) -> dict[str, Any]:
        return coverage_service.analyze_recent_signals(
            limit=payload.limit,
            create_suggestions=payload.create_suggestions,
            apply_safe_links=payload.apply_safe_links,
        )

    @router.get("/{signal_id}/link-coverage")
    async def get_signal_link_coverage(signal_id: str) -> dict[str, Any]:
        item = coverage_service.get_link_coverage(signal_id)
        return {"status": "OK" if item else "MISSING", "mock_data": False, "signal_id": signal_id, "link_coverage": item}

    @router.post("/{signal_id}/link-coverage/analyze")
    async def analyze_signal_link_coverage(signal_id: str, payload: AnalyzeOneLinkCoverageRequest) -> dict[str, Any]:
        item = coverage_service.analyze_signal(
            signal_id,
            create_suggestions=payload.create_suggestions,
            apply_safe_links=payload.apply_safe_links,
        )
        return {"status": "OK" if item else "MISSING", "mock_data": False, "signal_id": signal_id, "link_coverage": item}

    return router
