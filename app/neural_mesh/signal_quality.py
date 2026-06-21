from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


SignalQualityStatus = Literal[
    "GOOD",
    "PARTIAL",
    "WEAK",
    "STALE",
    "UNLINKED",
    "UNBOUND",
    "DRY_RUN_ONLY",
    "BLOCKED",
    "ERROR",
]


class SignalQualityEvaluation(BaseModel):
    signal_id: str
    quality_score: float = Field(ge=0, le=1)
    quality_status: SignalQualityStatus | str
    missing_fields: list[str] = Field(default_factory=list)
    readiness_reason: str | None = None
    can_feed_brain: bool = False
    can_feed_paper: bool = False
    has_market_id: bool = False
    has_source: bool = False
    has_lineage: bool = False
    has_correlation_id: bool = False
    has_raw_payload_ref: bool = False
    has_confidence: bool = False
    has_strength: bool = False
    has_freshness: bool = False
    has_evidence: bool = False
    linked_to_market: bool = False
    linked_to_position: bool = False
    used_by_brain_output: bool = False
    used_by_coordinator: bool = False
    is_dry_run_generated: bool = False
    is_runtime_generated: bool = False
    is_stale: bool = False
    evaluated_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("signal_id")
    @classmethod
    def require_signal_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("signal_id is required")
        return normalized

    @field_validator("quality_status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("quality_status is required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def signal_quality_from_row(row: dict[str, Any]) -> SignalQualityEvaluation:
    data = dict(row)
    data["missing_fields"] = data.pop("missing_fields_json", []) or []
    return SignalQualityEvaluation(**data)
