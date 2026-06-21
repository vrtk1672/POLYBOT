from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.control_center.action_contract import ControlCenterActionRequest
from app.control_center.action_service import ControlCenterActionService
from app.control_center.runtime_supervisor_wiring import build_runtime_supervisor
from app.runtime.state_governor import StateGovernor
from app.services.system_power import SystemPowerService


class SystemPowerRequest(BaseModel):
    actor: str | None = None
    reason: str | None = None
    correlation_id: str | None = None


def create_system_power_router(service: SystemPowerService | None = None) -> APIRouter:
    router = APIRouter(prefix="/system/power", tags=["system-power"])

    def _svc() -> SystemPowerService:
        return service or SystemPowerService()

    @router.get("")
    async def get_system_power() -> dict[str, Any]:
        return _svc().get_power_state()

    @router.post("/on")
    async def system_on(payload: SystemPowerRequest) -> dict[str, Any]:
        try:
            if service is not None:
                return _svc().turn_on(actor=payload.actor, reason=payload.reason, correlation_id=payload.correlation_id)
            envelope = _system_action("system-on", payload)
            if envelope.get("status") in {"REJECTED", "LOCKED", "ERROR"}:
                raise HTTPException(status_code=409 if envelope.get("status") == "LOCKED" else 400, detail=envelope)
            return _system_power_payload(envelope)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/off")
    async def system_off(payload: SystemPowerRequest) -> dict[str, Any]:
        try:
            if service is not None:
                return _svc().turn_off(actor=payload.actor, reason=payload.reason, correlation_id=payload.correlation_id)
            envelope = _system_action("system-off", payload)
            if envelope.get("status") in {"REJECTED", "LOCKED", "ERROR"}:
                raise HTTPException(status_code=409 if envelope.get("status") == "LOCKED" else 400, detail=envelope)
            return _system_power_payload(envelope)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router


def _system_action(action: str, payload: SystemPowerRequest) -> dict[str, Any]:
    governor = StateGovernor()
    envelope = ControlCenterActionService(
        governor=governor,
        runtime_supervisor=build_runtime_supervisor(governor=governor),
    ).execute(
        action,
        ControlCenterActionRequest(
            actor=payload.actor or "",
            reason=payload.reason or "",
        ),
    )
    return envelope.model_dump(mode="json")


def _system_power_payload(envelope: dict[str, Any]) -> dict[str, Any]:
    result = dict(envelope.get("result") or {})
    result["system_power_action"] = {
        "status": envelope.get("status"),
        "action": envelope.get("action"),
        "audit_id": envelope.get("audit_id"),
        "warnings": envelope.get("warnings") or [],
        "errors": envelope.get("errors") or [],
    }
    return result
