from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ProcessingState = Literal[
    "NEW",
    "LINKED",
    "QUALITY_CHECKED",
    "BRAIN_USED",
    "COORDINATOR_USED",
    "IGNORED",
    "STALE",
    "REJECTED",
    "ERROR",
]

GateStatus = Literal[
    "NOT_EVALUATED",
    "BLOCKED",
    "BRAIN_ELIGIBLE",
    "PAPER_BLOCKED",
    "PAPER_ELIGIBLE_INFORMATIONAL_ONLY",
    "STALE",
    "ERROR",
]


class SignalProcessingState(BaseModel):
    signal_id: str
    processing_state: ProcessingState | str
    previous_state: ProcessingState | str | None = None
    quality_evaluation_id: int | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    quality_status: str | None = None
    gate_status: GateStatus | str
    gate_blockers: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    linked_to_market: bool = False
    linked_to_position: bool = False
    used_by_brain_output: bool = False
    used_by_coordinator: bool = False
    is_dry_run_generated: bool = False
    is_runtime_generated: bool = False
    is_stale: bool = False
    can_feed_brain: bool = False
    can_feed_paper: bool = False
    rejection_reason: str | None = None
    ignored_reason: str | None = None
    error_reason: str | None = None
    evaluated_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None

    @field_validator("signal_id")
    @classmethod
    def require_signal_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("signal_id is required")
        return normalized

    @field_validator("processing_state", "previous_state", "gate_status", mode="before")
    @classmethod
    def normalize_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().upper()
        if not normalized:
            raise ValueError("state/status values must not be empty")
        return normalized

    @model_validator(mode="after")
    def require_reasons(self) -> "SignalProcessingState":
        if self.processing_state == "IGNORED" and not (self.ignored_reason or "").strip():
            raise ValueError("ignored_reason is required for IGNORED state")
        if self.processing_state == "ERROR" and not (self.error_reason or "").strip():
            raise ValueError("error_reason is required for ERROR state")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def signal_processing_from_row(row: dict[str, Any]) -> SignalProcessingState:
    data = dict(row)
    data["gate_blockers"] = data.pop("gate_blockers_json", []) or []
    data["missing_requirements"] = data.pop("missing_requirements_json", []) or []
    return SignalProcessingState(**data)
