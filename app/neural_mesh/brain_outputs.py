from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


BrainName = Literal[
    "context",
    "opportunity",
    "risk",
    "capital",
    "exit",
    "no_trade",
    "ai",
    "strategy",
    "memory",
    "execution_advisory",
    "unknown",
]

BrainOutputType = Literal[
    "INTERPRETATION",
    "WATCH",
    "CAUTION",
    "OPPORTUNITY_HINT",
    "RISK_WARNING",
    "NO_TRADE_HINT",
    "EXIT_REVIEW_HINT",
    "CAPITAL_NOTE",
    "AI_ANALYSIS",
    "STRATEGY_HINT",
    "MEMORY_NOTE",
]

BrainOutputStatus = Literal["ACTIVE", "PARTIAL", "DEGRADED", "STALE", "EXPIRED", "ERROR"]
DependencyType = Literal["signal", "brain_output", "event", "source"]
ConflictTargetType = Literal["brain_output", "signal", "source", "rule"]

FORBIDDEN_OUTPUT_KEYS = {
    "buy",
    "sell",
    "order",
    "order_id",
    "order_type",
    "limit_price",
    "market_order",
    "signed_request",
    "signature",
    "private_key",
    "place_order",
    "cancel_order",
    "execute_trade",
    "approved_for_trade",
    "bypass_risk",
    "bypass_governor",
}

FORBIDDEN_RECOMMENDATIONS = {
    "BUY",
    "SELL",
    "BUY_YES",
    "BUY_NO",
    "SELL_YES",
    "SELL_NO",
    "ENTER_TRADE",
    "EXIT_TRADE",
    "PLACE_ORDER",
    "CANCEL_ORDER",
    "APPROVED_FOR_TRADE",
}


class BrainOutputDependency(BaseModel):
    brain_output_id: str | None = None
    dependency_type: DependencyType
    dependency_id: str
    dependency_role: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime | None = None

    @field_validator("dependency_id")
    @classmethod
    def require_dependency_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("dependency_id is required")
        return normalized


class BrainOutputConflict(BaseModel):
    brain_output_id: str | None = None
    conflicts_with_type: ConflictTargetType
    conflicts_with_id: str
    conflict_type: str
    conflict_reason: str | None = None
    conflict_severity: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime | None = None

    @field_validator("conflicts_with_id", "conflict_type")
    @classmethod
    def require_conflict_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("conflict target and type are required")
        return normalized


class BrainOutput(BaseModel):
    brain_output_id: str = Field(default_factory=lambda: f"brain_output_{uuid4().hex}")
    brain: BrainName | str
    output_type: BrainOutputType | str
    market_id: str | None = None
    position_id: str | None = None
    recommendation: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    urgency: float | None = Field(default=None, ge=0, le=1)
    risk_flags: list[str] = Field(default_factory=list)
    reasoning_summary: str | None = None
    status: BrainOutputStatus | str
    ttl_seconds: int | None = Field(default=None, ge=0)
    expires_at: datetime | None = None
    correlation_id: str | None = None
    generated_by: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    raw_payload_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("brain")
    @classmethod
    def normalize_brain(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("brain is required")
        return normalized

    @field_validator("output_type", "status")
    @classmethod
    def normalize_upper_text(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("output_type and status are required")
        return normalized

    @field_validator("recommendation")
    @classmethod
    def require_recommendation(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("recommendation is required")
        if normalized.upper() in FORBIDDEN_RECOMMENDATIONS:
            raise ValueError("brain output recommendation must not be an executable trade action")
        return normalized

    @model_validator(mode="after")
    def reject_executable_payload(self) -> "BrainOutput":
        forbidden = _find_forbidden_keys(self.metadata)
        if forbidden:
            raise ValueError(f"brain output metadata contains executable/order keys: {sorted(forbidden)}")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def brain_output_from_row(row: dict[str, Any]) -> BrainOutput:
    data = dict(row)
    data["risk_flags"] = data.pop("risk_flags_json", []) or []
    data["metadata"] = data.pop("metadata_json", {}) or {}
    return BrainOutput(**data)


def dependency_from_row(row: dict[str, Any]) -> BrainOutputDependency:
    return BrainOutputDependency(**dict(row))


def conflict_from_row(row: dict[str, Any]) -> BrainOutputConflict:
    return BrainOutputConflict(**dict(row))


def _find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_OUTPUT_KEYS:
                found.add(normalized)
            found.update(_find_forbidden_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_forbidden_keys(item))
    return found
