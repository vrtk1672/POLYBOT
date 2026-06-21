from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ExitPlanStatus = Literal["COMPLETE", "INCOMPLETE", "BLOCKED", "ERROR"]
ExitPlanType = Literal[
    "BASIC_PROTECTIVE_EXIT",
    "BLOCKED_NO_ENTRY_EXIT",
    "LIQUIDITY_PROTECTION_EXIT",
    "TIME_ONLY_EXIT",
    "EMERGENCY_ONLY_EXIT",
]


class ExitFoundationPlan(BaseModel):
    exit_plan_id: str
    thesis_id: str | None = None
    risk_decision_id: str | None = None
    market_id: str | None = None
    side: str | None = None
    status: ExitPlanStatus | str
    exit_type: ExitPlanType | str
    target_exit: float | None = Field(default=None, ge=0.01, le=0.99)
    stop_loss: float | None = Field(default=None, ge=0.01, le=0.99)
    max_hold_seconds: int = Field(default=3600, ge=1)
    invalidation_rules: list[str] = Field(default_factory=list)
    emergency_exit_rules: list[str] = Field(default_factory=list)
    liquidity_exit_check: dict[str, Any] = Field(default_factory=dict)
    time_exit_check: dict[str, Any] = Field(default_factory=dict)
    missing_exit_evidence: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_risk_status: str | None = None
    source_risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    orderbook_snapshot_id: int | None = None
    paper_intent_allowed: bool = False
    paper_exit_ready: bool = False
    execution_allowed: bool = False
    generated_by: str = "runtime"
    producer_name: str = "exit_foundation"
    is_runtime_generated: bool = True
    is_dry_run_generated: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("exit_plan_id", "status", "exit_type")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("exit plan requires exit_plan_id, status, and exit_type")
        return normalized

    @field_validator("status", "exit_type")
    @classmethod
    def uppercase(cls, value: str) -> str:
        return (value or "").strip().upper()

    @field_validator("side")
    @classmethod
    def normalize_side(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().upper()
        return normalized or None

    @field_validator("invalidation_rules", "emergency_exit_rules", "missing_exit_evidence", "blockers", "warnings")
    @classmethod
    def clean_list(cls, value: list[str]) -> list[str]:
        return sorted({str(item).strip().upper() for item in value or [] if str(item).strip()})

    @model_validator(mode="after")
    def enforce_exit_safety(self) -> "ExitFoundationPlan":
        if self.paper_intent_allowed:
            raise ValueError("4C-Q exit plans cannot allow Paper intents")
        if self.execution_allowed:
            raise ValueError("4C-Q exit plans cannot allow execution")
        if self.status == "COMPLETE":
            if self.target_exit is None or self.stop_loss is None:
                raise ValueError("COMPLETE exit plan requires target_exit and stop_loss")
            if not self.market_id or not self.side or not self.orderbook_snapshot_id:
                raise ValueError("COMPLETE exit plan requires market, side, and orderbook")
            if not self.invalidation_rules or not self.emergency_exit_rules or not self.liquidity_exit_check:
                raise ValueError("COMPLETE exit plan requires exit rules")
        if self.status in {"BLOCKED", "INCOMPLETE"} and self.paper_exit_ready:
            raise ValueError("blocked or incomplete exit plan cannot be paper-exit ready")
        if self.generated_by == "runtime" and self.is_dry_run_generated:
            raise ValueError("runtime exit plan cannot be dry-run generated")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ExitFoundationRun(BaseModel):
    mock_data: bool = False
    run_id: str
    status: str
    risk_decisions_checked: int = Field(default=0, ge=0)
    exit_plans_created: int = Field(default=0, ge=0)
    exit_plans_updated: int = Field(default=0, ge=0)
    complete_exit_count: int = Field(default=0, ge=0)
    incomplete_exit_count: int = Field(default=0, ge=0)
    blocked_exit_count: int = Field(default=0, ge=0)
    missing_market_count: int = Field(default=0, ge=0)
    missing_orderbook_count: int = Field(default=0, ge=0)
    missing_side_count: int = Field(default=0, ge=0)
    missing_risk_approval_count: int = Field(default=0, ge=0)
    paper_ready_before: bool = False
    paper_ready_after: bool = False
    orders_created: int = 0
    order_intents_created: int = 0
    fills_created: int = 0
    positions_created: int = 0
    live_actions_created: int = 0
    plans: list[ExitFoundationPlan] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None

    @model_validator(mode="after")
    def enforce_non_executing_run(self) -> "ExitFoundationRun":
        if self.mock_data:
            raise ValueError("Exit Foundation run cannot return mock data")
        if self.paper_ready_before or self.paper_ready_after:
            raise ValueError("Exit Foundation run must not mark Paper ready")
        if any(
            value != 0
            for value in (
                self.orders_created,
                self.order_intents_created,
                self.fills_created,
                self.positions_created,
                self.live_actions_created,
            )
        ):
            raise ValueError("Exit Foundation run created executable artifacts")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
