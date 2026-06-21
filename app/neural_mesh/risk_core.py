from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


RiskDecisionValue = Literal["APPROVE", "REJECT", "BLOCK", "WARN_ONLY", "ERROR"]
RiskStatusValue = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "BLOCKED", "ERROR"]


class RiskDecision(BaseModel):
    risk_decision_id: str
    thesis_id: str
    market_id: str | None = None
    decision: RiskDecisionValue | str
    risk_status: RiskStatusValue | str
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    max_position_size: float = Field(default=10.0, ge=0.0)
    max_loss: float = Field(default=5.0, ge=0.0)
    market_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    liquidity_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    spread_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_data_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    daily_exposure_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_missing_evidence: list[str] = Field(default_factory=list)
    source_thesis_status: str | None = None
    orderbook_snapshot_id: int | None = None
    paper_candidate_allowed: bool = False
    execution_allowed: bool = False
    risk_approved: bool = False
    exit_required: bool = True
    generated_by: str = "runtime"
    producer_name: str = "risk_core"
    is_runtime_generated: bool = True
    is_dry_run_generated: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("risk_decision_id", "thesis_id", "decision", "risk_status")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("risk decision requires id, thesis_id, decision, and status")
        return normalized

    @field_validator("decision", "risk_status")
    @classmethod
    def uppercase(cls, value: str) -> str:
        return (value or "").strip().upper()

    @field_validator("risk_reasons", "blockers", "warnings", "required_missing_evidence")
    @classmethod
    def clean_list(cls, value: list[str]) -> list[str]:
        return sorted({str(item).strip().upper() for item in value or [] if str(item).strip()})

    @model_validator(mode="after")
    def enforce_non_executing(self) -> "RiskDecision":
        if self.paper_candidate_allowed:
            raise ValueError("4C-P risk decisions cannot allow Paper candidates")
        if self.execution_allowed:
            raise ValueError("4C-P risk decisions cannot allow execution")
        if self.generated_by == "runtime" and self.is_dry_run_generated:
            raise ValueError("runtime risk decisions cannot be dry-run generated")
        if self.decision == "APPROVE" and self.blockers:
            raise ValueError("approved risk decision cannot contain blockers")
        if self.decision in {"BLOCK", "REJECT"} and self.risk_approved:
            raise ValueError("blocked or rejected risk decision cannot be risk approved")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RiskCoreRun(BaseModel):
    mock_data: bool = False
    run_id: str
    status: str
    thesis_profiles_checked: int = Field(default=0, ge=0)
    risk_decisions_created: int = Field(default=0, ge=0)
    risk_decisions_updated: int = Field(default=0, ge=0)
    approved_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    blocked_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    max_position_size_default: float = Field(default=10.0, ge=0.0)
    max_loss_default: float = Field(default=5.0, ge=0.0)
    confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    paper_ready_before: bool = False
    paper_ready_after: bool = False
    orders_created: int = 0
    order_intents_created: int = 0
    fills_created: int = 0
    positions_created: int = 0
    live_actions_created: int = 0
    decisions: list[RiskDecision] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None

    @model_validator(mode="after")
    def enforce_non_executing_run(self) -> "RiskCoreRun":
        if self.mock_data:
            raise ValueError("Risk Core run cannot return mock data")
        if self.paper_ready_before or self.paper_ready_after:
            raise ValueError("Risk Core run must not mark Paper ready")
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
            raise ValueError("Risk Core run created executable artifacts")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
