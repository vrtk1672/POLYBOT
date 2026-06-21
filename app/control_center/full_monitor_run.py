from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


FullMonitorRunStatus = Literal[
    "ACCEPTED",
    "IDLE",
    "STARTING",
    "RUNNING",
    "STOPPING",
    "STOPPED",
    "COMPLETED",
    "FAILED",
    "REJECTED",
    "ERROR",
    "LOCKED",
    "NOT_IMPLEMENTED",
]

ModuleRunStatus = Literal["COMPLETED", "SKIPPED", "NOT_IMPLEMENTED", "ERROR"]


class FullMonitorRunRequest(BaseModel):
    actor: str = Field(default="")
    reason: str = Field(default="")
    duration_minutes: int | None = None
    interval_seconds: int | None = None
    max_cycles: int = Field(default=1, ge=1, le=10)


class FullMonitorStopRequest(BaseModel):
    actor: str = Field(default="")
    reason: str = Field(default="")


class FullMonitorModuleResult(BaseModel):
    module: str
    status: ModuleRunStatus
    behavior: str
    source: str | None = None
    counters: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class FullMonitorRunRecord(BaseModel):
    run_type: Literal["FULL_MONITOR_RUN"] = "FULL_MONITOR_RUN"
    run_id: str
    status: FullMonitorRunStatus
    started_at: str
    updated_at: str | None = None
    stopped_at: str | None = None
    ended_at: str | None = None
    completed_at: str | None = None
    requested_duration_minutes: int
    duration_minutes: int | None = None
    interval_seconds: int = 60
    elapsed_seconds: float = 0.0
    remaining_seconds: float = 0.0
    next_cycle_in_seconds: float | None = None
    cycles_completed: int = 0
    markets_checked: int = 0
    events_created: int = 0
    events_seen: int = 0
    opportunities_found: int = 0
    no_trades_logged: int = 0
    modules_completed: int = 0
    modules_skipped: int = 0
    paper_orders: int = 0
    paper_fills: int = 0
    positions_updated: int = 0
    module_results: list[FullMonitorModuleResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_id: str
    actor: str
    reason: str
    max_cycles: int = 1
    report_path: str | None = None
    report_json_path: str | None = None
    safety_mode: Literal["DATA_ONLY_MONITORING"] = "DATA_ONLY_MONITORING"
    execution_enabled: bool = False

    def to_action_result(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
