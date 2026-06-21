from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ThesisProfileStatus = Literal["COMPLETE", "INCOMPLETE", "BLOCKED", "WEAK", "ERROR"]
ThesisProfileType = Literal[
    "RUNTIME_COORDINATOR_THESIS",
    "BLOCKED_NO_TRADE_THESIS",
    "HOLD_FOR_MORE_EVIDENCE",
    "WEAK_SIGNAL_THESIS",
]


class ThesisProfile(BaseModel):
    thesis_id: str
    market_id: str | None = None
    side: str | None = None
    status: ThesisProfileStatus | str
    thesis_type: ThesisProfileType | str
    why_now: str
    expected_move: str | None = "UNKNOWN"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)
    missing_evidence: list[str] = Field(default_factory=list)
    invalidation_rules: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    source_coordinator_decision_id: str | None = None
    source_brain_output_ids: list[str] = Field(default_factory=list)
    source_signal_ids: list[str] = Field(default_factory=list)
    orderbook_snapshot_id: int | None = None
    generated_by: str = "runtime"
    producer_name: str = "thesis_profile_builder"
    is_runtime_generated: bool = True
    is_dry_run_generated: bool = False
    paper_candidate_allowed: bool = False
    risk_required: bool = True
    exit_required: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("thesis_id", "status", "thesis_type", "why_now")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("thesis profile requires thesis_id, status, thesis_type, and why_now")
        return normalized

    @field_validator("status", "thesis_type")
    @classmethod
    def uppercase(cls, value: str) -> str:
        return (value or "").strip().upper()

    @field_validator("generated_by")
    @classmethod
    def normalize_generated_by(cls, value: str) -> str:
        normalized = (value or "runtime").strip().lower()
        if normalized not in {"runtime", "dry_run", "adapter", "manual", "unknown"}:
            raise ValueError("generated_by must be runtime, dry_run, adapter, manual, or unknown")
        return normalized

    @field_validator("missing_evidence", "invalidation_rules", "risk_notes", "source_brain_output_ids", "source_signal_ids")
    @classmethod
    def clean_list(cls, value: list[str]) -> list[str]:
        return [str(item).strip() for item in value or [] if str(item).strip()]

    @model_validator(mode="after")
    def enforce_paper_safety(self) -> "ThesisProfile":
        if self.paper_candidate_allowed:
            raise ValueError("4C-O thesis profiles cannot allow Paper candidates")
        if self.status == "COMPLETE" and not self.market_id:
            raise ValueError("COMPLETE thesis requires market_id")
        if self.status == "COMPLETE" and self.missing_evidence:
            raise ValueError("COMPLETE thesis cannot have missing evidence")
        if self.generated_by == "runtime" and self.is_dry_run_generated:
            raise ValueError("runtime thesis cannot be dry-run generated")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ThesisProfileRun(BaseModel):
    mock_data: bool = False
    run_id: str
    status: str
    coordinator_decisions_checked: int = Field(default=0, ge=0)
    eligible_decisions: int = Field(default=0, ge=0)
    thesis_profiles_created: int = Field(default=0, ge=0)
    thesis_profiles_updated: int = Field(default=0, ge=0)
    complete_thesis_count: int = Field(default=0, ge=0)
    incomplete_thesis_count: int = Field(default=0, ge=0)
    blocked_thesis_count: int = Field(default=0, ge=0)
    weak_thesis_count: int = Field(default=0, ge=0)
    missing_market_count: int = Field(default=0, ge=0)
    missing_orderbook_count: int = Field(default=0, ge=0)
    missing_binding_count: int = Field(default=0, ge=0)
    missing_evidence_count: int = Field(default=0, ge=0)
    paper_ready_before: bool = False
    paper_ready_after: bool = False
    orders_created: int = 0
    order_intents_created: int = 0
    fills_created: int = 0
    positions_created: int = 0
    live_actions_created: int = 0
    profiles: list[ThesisProfile] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None

    @model_validator(mode="after")
    def enforce_non_executing(self) -> "ThesisProfileRun":
        if self.mock_data:
            raise ValueError("thesis profile run cannot return mock data")
        if self.paper_ready_before or self.paper_ready_after:
            raise ValueError("thesis profile run must not mark Paper ready")
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
            raise ValueError("thesis profile run created executable artifacts")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
