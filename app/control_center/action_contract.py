from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ControlCenterActionName = Literal[
    "system-on",
    "system-off",
    "start-full-monitor-run",
    "stop-current-run",
    "kill-switch",
    "enable-paper-simulation",
    "disable-paper-simulation",
    "reset-paper-balance",
]

ControlCenterActionStatus = Literal["ACCEPTED", "REJECTED", "LOCKED", "NOT_IMPLEMENTED", "ERROR"]


class ControlCenterActionRequest(BaseModel):
    actor: str = Field(default="")
    reason: str = Field(default="")
    confirmation: str | None = None
    duration_minutes: int | None = None
    interval_seconds: int | None = None
    max_cycles: int | None = Field(default=None, ge=1, le=10)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlCenterSafetyCheck(BaseModel):
    name: str
    status: Literal["PASS", "FAIL", "LOCKED", "NOT_IMPLEMENTED"]
    detail: str


class ControlCenterActionEnvelope(BaseModel):
    action: str
    status: ControlCenterActionStatus
    actor: str
    reason: str
    timestamp: str
    audit_id: str | None = None
    state_before: dict[str, Any] = Field(default_factory=dict)
    state_after: dict[str, Any] = Field(default_factory=dict)
    safety_checks: list[ControlCenterSafetyCheck] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def action_timestamp() -> str:
    return datetime.now(UTC).isoformat()
