from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


CoordinatorFinalState = Literal[
    "NO_TRADE",
    "WATCH",
    "REVIEW_REQUIRED",
    "PAPER_CANDIDATE_BLOCKED",
    "EXIT_REVIEW_REQUIRED",
    "RISK_BLOCKED",
    "INSUFFICIENT_DATA",
    "CONFLICT_REVIEW",
    "DATA_DEGRADED",
]

CoordinatorStatus = Literal["ACTIVE", "PARTIAL", "DEGRADED", "STALE", "EXPIRED", "ERROR"]

APPROVED_ACTIONS = {
    "NONE",
    "WATCH",
    "REVIEW",
    "REQUEST_MORE_DATA",
    "MARK_NO_TRADE",
    "SEND_TO_RISK_REVIEW",
    "SEND_TO_EXIT_REVIEW",
    "SEND_TO_HUMAN_REVIEW",
}

BLOCKED_ACTIONS = {
    "PAPER_ENTRY",
    "LIVE_ENTRY",
    "ORDER_CREATION",
    "POSITION_OPEN",
    "POSITION_CLOSE",
    "EXECUTION",
    "AI_OVERRIDE",
    "OPPORTUNITY_OVERRIDE_RISK",
}

EXECUTABLE_FINAL_STATES = {
    "BUY",
    "SELL",
    "ENTER_TRADE",
    "EXIT_TRADE",
    "PLACE_ORDER",
    "CANCEL_ORDER",
    "LIVE_APPROVED",
    "EXECUTE",
}

EXECUTABLE_APPROVED_ACTIONS = BLOCKED_ACTIONS.union(
    {
        "BUY",
        "SELL",
        "ENTER_TRADE",
        "EXIT_TRADE",
        "PLACE_ORDER",
        "CANCEL_ORDER",
        "LIVE_APPROVED",
        "EXECUTE",
    }
)


class CoordinatorDecisionInput(BaseModel):
    coordinator_decision_id: str | None = None
    brain_output_id: str
    brain: str
    input_role: str | None = None
    input_recommendation: str | None = None
    input_confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime | None = None

    @field_validator("brain_output_id", "brain")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("brain output id and brain are required")
        return normalized


class CoordinatorDecisionConflict(BaseModel):
    coordinator_decision_id: str | None = None
    conflict_type: str
    conflict_key: str
    conflict_reason: str
    conflict_severity: float | None = Field(default=None, ge=0, le=1)
    left_brain: str | None = None
    right_brain: str | None = None
    left_output_id: str | None = None
    right_output_id: str | None = None
    created_at: datetime | None = None

    @field_validator("conflict_type", "conflict_key", "conflict_reason")
    @classmethod
    def require_conflict_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("conflict type, key, and reason are required")
        return normalized


class CoordinatorDecision(BaseModel):
    coordinator_decision_id: str = Field(default_factory=lambda: f"coord_{uuid4().hex}")
    market_id: str | None = None
    position_id: str | None = None
    final_state: CoordinatorFinalState | str
    primary_reason: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    urgency: float | None = Field(default=None, ge=0, le=1)
    conflicts_detected: bool = False
    governor_required: bool = True
    execution_allowed: bool = False
    approved_actions: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)
    required_reviews: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    source_brain_count: int = Field(default=0, ge=0)
    input_output_count: int = Field(default=0, ge=0)
    conflict_count: int = Field(default=0, ge=0)
    correlation_id: str | None = None
    ttl_seconds: int | None = Field(default=None, ge=0)
    expires_at: datetime | None = None
    status: CoordinatorStatus | str = "ACTIVE"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("final_state")
    @classmethod
    def validate_final_state(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("final_state is required")
        if normalized in EXECUTABLE_FINAL_STATES:
            raise ValueError("coordinator final_state must not be executable")
        return normalized

    @field_validator("primary_reason")
    @classmethod
    def require_primary_reason(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("primary_reason is required")
        return normalized

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("status is required")
        return normalized

    @field_validator("approved_actions", "blocked_actions", "required_reviews", "risk_flags")
    @classmethod
    def normalize_list(cls, value: list[str]) -> list[str]:
        return [str(item).strip().upper() for item in value if str(item).strip()]

    @model_validator(mode="after")
    def enforce_non_executing(self) -> "CoordinatorDecision":
        if self.execution_allowed:
            raise ValueError("execution_allowed must remain false")
        executable = sorted(set(self.approved_actions).intersection(EXECUTABLE_APPROVED_ACTIONS))
        if executable:
            raise ValueError(f"approved_actions contains executable actions: {executable}")
        unknown = sorted(set(self.approved_actions) - APPROVED_ACTIONS)
        if unknown:
            raise ValueError(f"approved_actions contains unknown actions: {unknown}")
        invalid_blocked = sorted(set(self.blocked_actions) - BLOCKED_ACTIONS)
        if invalid_blocked:
            raise ValueError(f"blocked_actions contains unknown actions: {invalid_blocked}")
        if self.conflicts_detected and self.conflict_count <= 0 and not self.metadata.get("conflicts"):
            raise ValueError("conflicts_detected requires conflict rows or conflict metadata")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def coordinator_decision_from_row(row: dict[str, Any]) -> CoordinatorDecision:
    data = dict(row)
    data["approved_actions"] = data.pop("approved_actions_json", []) or []
    data["blocked_actions"] = data.pop("blocked_actions_json", []) or []
    data["required_reviews"] = data.pop("required_reviews_json", []) or []
    data["risk_flags"] = data.pop("risk_flags_json", []) or []
    data["metadata"] = data.pop("metadata_json", {}) or {}
    return CoordinatorDecision(**data)


def coordinator_input_from_row(row: dict[str, Any]) -> CoordinatorDecisionInput:
    return CoordinatorDecisionInput(**dict(row))


def coordinator_conflict_from_row(row: dict[str, Any]) -> CoordinatorDecisionConflict:
    return CoordinatorDecisionConflict(**dict(row))
