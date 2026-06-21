from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from app.db.connection import DatabaseConnectionFactory
from app.services.position_thesis import PositionThesisService


class PositionThesisProfileRequest(BaseModel):
    position_id: str
    market_id: str
    side: str = "UNKNOWN"
    entry_thesis: str
    profit_drivers: list[str] = Field(default_factory=list)
    invalidation_drivers: list[str] = Field(default_factory=list)
    watch_entities: list[str] = Field(default_factory=list)
    danger_signals: list[str] = Field(default_factory=list)
    take_profit_rules: list[str] = Field(default_factory=list)
    partial_exit_rules: list[str] = Field(default_factory=list)
    emergency_exit_rules: list[str] = Field(default_factory=list)
    status: str = "DRAFT"
    coordinator_decision_id: str | None = None
    brain_output_id: str | None = None
    source_signal_ids: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    thesis_version: int = Field(default=1, ge=1)
    created_by: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PositionThesisUpdateRequest(BaseModel):
    side: str | None = None
    entry_thesis: str | None = None
    profit_drivers: list[str] | None = None
    invalidation_drivers: list[str] | None = None
    watch_entities: list[str] | None = None
    danger_signals: list[str] | None = None
    take_profit_rules: list[str] | None = None
    partial_exit_rules: list[str] | None = None
    emergency_exit_rules: list[str] | None = None
    status: str | None = None
    coordinator_decision_id: str | None = None
    brain_output_id: str | None = None
    source_signal_ids: list[str] | None = None
    risk_flags: list[str] | None = None
    thesis_version: int | None = Field(default=None, ge=1)
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] | None = None


def create_position_thesis_router(
    *,
    connection_factory: DatabaseConnectionFactory | None = None,
    service: PositionThesisService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/thesis", tags=["position-thesis"])
    factory = connection_factory or DatabaseConnectionFactory()
    thesis_service = service or PositionThesisService(connection_factory=factory)

    @router.get("/profiles")
    async def list_profiles(
        status: str | None = Query(default=None),
        market_id: str | None = Query(default=None),
        position_id: str | None = Query(default=None),
        paper_ready: bool | None = Query(default=None),
        live_ready: bool | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        profiles = thesis_service.list_thesis_profiles(
            status=status,
            market_id=market_id,
            position_id=position_id,
            paper_ready=paper_ready,
            live_ready=live_ready,
            limit=limit,
        )
        return {"status": "OK", "mock_data": False, "count": len(profiles), "profiles": profiles}

    @router.get("/profiles/{thesis_id}")
    async def get_profile(thesis_id: str) -> dict[str, Any]:
        profile = thesis_service.get_thesis_by_id(thesis_id)
        return {"status": "OK" if profile else "MISSING", "mock_data": False, "thesis_id": thesis_id, "profile": profile}

    @router.get("/positions/{position_id}")
    async def get_position_thesis(position_id: str) -> dict[str, Any]:
        profile = thesis_service.get_thesis_by_position(position_id)
        return {"status": "OK" if profile else "MISSING", "mock_data": False, "position_id": position_id, "profile": profile}

    @router.get("/positions/{position_id}/validation")
    async def position_validation(position_id: str) -> dict[str, Any]:
        validation = thesis_service.check_thesis_required_for_position(position_id)
        return {"status": "OK" if validation["thesis_present"] else "MISSING", "mock_data": False, **validation}

    @router.get("/summary")
    async def summary(limit: int = Query(default=10, ge=1, le=100)) -> dict[str, Any]:
        return thesis_service.get_thesis_summary(limit=limit)

    @router.post("/profiles")
    async def create_profile(payload: PositionThesisProfileRequest) -> dict[str, Any]:
        try:
            profile = thesis_service.create_position_thesis_profile(payload.model_dump())
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"status": "OK", "mock_data": False, "profile": profile}

    @router.put("/profiles/{thesis_id}")
    async def update_profile(thesis_id: str, payload: PositionThesisUpdateRequest) -> dict[str, Any]:
        updates = payload.model_dump(exclude_none=True)
        try:
            profile = thesis_service.update_position_thesis_profile(thesis_id, updates)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"status": "OK", "mock_data": False, "profile": profile}

    @router.post("/profiles/{thesis_id}/validate")
    async def validate_profile(thesis_id: str) -> dict[str, Any]:
        try:
            validation = thesis_service.validate_thesis_profile(thesis_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "OK", "mock_data": False, "thesis_id": thesis_id, "validation": validation}

    @router.post("/profiles/{thesis_id}/needs-review")
    async def mark_needs_review(thesis_id: str) -> dict[str, Any]:
        try:
            profile = thesis_service.mark_thesis_needs_review(thesis_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "OK", "mock_data": False, "profile": profile}

    @router.post("/profiles/{thesis_id}/invalidate")
    async def mark_invalidated(thesis_id: str) -> dict[str, Any]:
        try:
            profile = thesis_service.mark_thesis_invalidated(thesis_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "OK", "mock_data": False, "profile": profile}

    return router
