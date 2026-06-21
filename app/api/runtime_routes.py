from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.events.event_bus import EventBus
from app.events.types import EventType
from app.runtime.health_truth import HealthTruthService
from app.runtime.modes import parse_runtime_mode
from app.runtime.runtime_errors import RuntimeModeTransitionDenied, RuntimeStateUnavailable
from app.runtime.state_governor import StateGovernor


class ModeRequest(BaseModel):
    to_mode: str
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeControlRequest(BaseModel):
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResumeRequest(RuntimeControlRequest):
    target_mode: str = "DATA_ONLY"


def create_runtime_router(
    *,
    governor: StateGovernor | None = None,
    health_service: HealthTruthService | None = None,
    event_bus: EventBus | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/runtime", tags=["runtime"])
    governor = governor or StateGovernor()
    health_service = health_service or HealthTruthService()
    event_bus = event_bus or EventBus()

    @router.get("/state")
    async def runtime_state() -> dict[str, object]:
        try:
            state = governor.get_current_state()
            permissions = governor.get_permissions()
            return {"state": state.to_dict(), "permissions": permissions.to_dict()}
        except RuntimeStateUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/health")
    async def runtime_health() -> dict[str, object]:
        return health_service.get_health_truth()

    @router.get("/mode")
    async def runtime_mode() -> dict[str, object]:
        try:
            state = governor.get_current_state()
            permissions = governor.get_permissions()
            return {"current_mode": state.current_mode.value, "permissions": permissions.to_dict()}
        except RuntimeStateUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/mode/request")
    async def request_mode_change(payload: ModeRequest) -> dict[str, object]:
        try:
            parse_runtime_mode(payload.to_mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"blocked_reason": str(exc)}) from exc
        try:
            state = governor.request_mode_change(
                payload.to_mode,
                actor=payload.actor,
                reason=payload.reason,
                metadata=payload.metadata,
            )
            _publish_mode_changed(event_bus, state.to_dict(), payload.actor, payload.reason)
            return {"state": state.to_dict(), "permissions": governor.get_permissions().to_dict()}
        except RuntimeModeTransitionDenied as exc:
            raise HTTPException(status_code=409, detail={"blocked_reason": str(exc)}) from exc

    @router.post("/kill")
    async def runtime_kill(payload: RuntimeControlRequest) -> dict[str, object]:
        state = governor.activate_kill(actor=payload.actor, reason=payload.reason, metadata=payload.metadata)
        _publish_mode_changed(event_bus, state.to_dict(), payload.actor, payload.reason)
        return {"state": state.to_dict(), "permissions": governor.get_permissions().to_dict()}

    @router.post("/resume")
    async def runtime_resume(payload: ResumeRequest) -> dict[str, object]:
        try:
            parse_runtime_mode(payload.target_mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"blocked_reason": str(exc)}) from exc
        try:
            state = governor.resume_from_kill(
                actor=payload.actor,
                reason=payload.reason,
                target_mode=payload.target_mode,
                metadata=payload.metadata,
            )
            _publish_mode_changed(event_bus, state.to_dict(), payload.actor, payload.reason)
            return {"state": state.to_dict(), "permissions": governor.get_permissions().to_dict()}
        except RuntimeModeTransitionDenied as exc:
            raise HTTPException(status_code=409, detail={"blocked_reason": str(exc)}) from exc

    return router


def _publish_mode_changed(event_bus: EventBus, state: dict[str, object], actor: str, reason: str) -> None:
    try:
        event_bus.publish(
            EventType.RUNTIME_MODE_CHANGED.value,
            {
                "current_mode": state.get("current_mode"),
                "previous_mode": state.get("previous_mode"),
                "actor": actor,
                "reason": reason,
            },
            source_service="runtime_api",
            aggregate_type="runtime_state",
            aggregate_id=str(state.get("id") or "current"),
            correlation_id=state.get("correlation_id") if isinstance(state.get("correlation_id"), str) else None,
            metadata={"non_trading_event": True},
        )
    except Exception:
        pass
