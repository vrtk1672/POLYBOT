from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PaperEligibilityStatus = Literal["ELIGIBLE", "INELIGIBLE", "BLOCKED", "INCOMPLETE", "ERROR"]


class PaperEligibilityCandidate(BaseModel):
    eligibility_id: str
    thesis_id: str | None = None
    risk_decision_id: str | None = None
    exit_plan_id: str | None = None
    coordinator_decision_id: str | None = None
    brain_output_ids: list[str] = Field(default_factory=list)
    signal_ids: list[str] = Field(default_factory=list)
    market_id: str | None = None
    side: str | None = None
    status: PaperEligibilityStatus | str
    eligibility_score: float = Field(default=0.0, ge=0.0, le=1.0)
    eligibility_blockers: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    orderbook_snapshot_id: int | None = None
    link_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    lineage_trusted: bool = False
    risk_approved: bool = False
    exit_ready: bool = False
    not_dry_run: bool = False
    paper_intent_allowed: bool = False
    execution_allowed: bool = False
    generated_by: str = "runtime"
    producer_name: str = "paper_eligibility_gate"
    is_runtime_generated: bool = True
    is_dry_run_generated: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("eligibility_id", "status")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("paper eligibility candidate requires eligibility_id and status")
        return normalized

    @field_validator("status")
    @classmethod
    def uppercase_status(cls, value: str) -> str:
        return (value or "").strip().upper()

    @field_validator("side")
    @classmethod
    def normalize_side(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().upper()
        return normalized or None

    @field_validator("eligibility_blockers", "missing_requirements")
    @classmethod
    def clean_codes(cls, value: list[str]) -> list[str]:
        return sorted({str(item).strip().upper() for item in value or [] if str(item).strip()})

    @field_validator("brain_output_ids", "signal_ids")
    @classmethod
    def clean_ids(cls, value: list[str]) -> list[str]:
        return sorted({str(item).strip() for item in value or [] if str(item).strip()})

    @model_validator(mode="after")
    def enforce_safety(self) -> "PaperEligibilityCandidate":
        if self.paper_intent_allowed:
            raise ValueError("4C-R eligibility candidates cannot allow Paper intents")
        if self.execution_allowed:
            raise ValueError("4C-R eligibility candidates cannot allow execution")
        if self.status == "ELIGIBLE":
            required = {
                "thesis_id": self.thesis_id,
                "risk_decision_id": self.risk_decision_id,
                "exit_plan_id": self.exit_plan_id,
                "market_id": self.market_id,
                "side": self.side,
                "orderbook_snapshot_id": self.orderbook_snapshot_id,
            }
            missing = [key for key, value in required.items() if value in (None, "", [])]
            if missing:
                raise ValueError(f"ELIGIBLE candidate missing mandatory fields: {missing}")
            if not self.risk_approved or not self.exit_ready or not self.lineage_trusted or not self.not_dry_run:
                raise ValueError("ELIGIBLE candidate requires risk, exit, lineage, and runtime provenance")
            if not self.signal_ids or not self.brain_output_ids or not self.coordinator_decision_id:
                raise ValueError("ELIGIBLE candidate requires signal, brain, and coordinator evidence")
            if self.eligibility_blockers or self.missing_requirements:
                raise ValueError("ELIGIBLE candidate cannot carry blockers or missing requirements")
        if self.generated_by == "runtime" and self.is_dry_run_generated:
            raise ValueError("runtime eligibility candidate cannot be dry-run generated")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PaperEligibilityRun(BaseModel):
    mock_data: bool = False
    run_id: str
    status: str
    exit_plans_checked: int = Field(default=0, ge=0)
    candidates_created: int = Field(default=0, ge=0)
    candidates_updated: int = Field(default=0, ge=0)
    eligible_count: int = Field(default=0, ge=0)
    ineligible_count: int = Field(default=0, ge=0)
    blocked_count: int = Field(default=0, ge=0)
    incomplete_count: int = Field(default=0, ge=0)
    missing_exit_plan_count: int = Field(default=0, ge=0)
    missing_risk_decision_count: int = Field(default=0, ge=0)
    missing_thesis_count: int = Field(default=0, ge=0)
    missing_market_count: int = Field(default=0, ge=0)
    missing_orderbook_count: int = Field(default=0, ge=0)
    missing_binding_count: int = Field(default=0, ge=0)
    missing_lineage_count: int = Field(default=0, ge=0)
    dry_run_blocked_count: int = Field(default=0, ge=0)
    paper_ready_before: bool = False
    paper_ready_after: bool = False
    orders_created: int = 0
    order_intents_created: int = 0
    fills_created: int = 0
    positions_created: int = 0
    live_actions_created: int = 0
    candidates: list[PaperEligibilityCandidate] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None

    @model_validator(mode="after")
    def enforce_non_executing_run(self) -> "PaperEligibilityRun":
        if self.mock_data:
            raise ValueError("Paper Eligibility run cannot return mock data")
        if self.paper_ready_before or self.paper_ready_after:
            raise ValueError("Paper Eligibility run must not mark Paper ready")
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
            raise ValueError("Paper Eligibility run created executable artifacts")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
