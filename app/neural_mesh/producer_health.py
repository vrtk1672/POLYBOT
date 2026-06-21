from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ProducerHealthStatus = Literal[
    "HEALTHY",
    "ACTIVE",
    "DEGRADED",
    "SILENT",
    "MISSING",
    "DRY_RUN_ONLY",
    "REGISTERED_ONLY",
    "UNKNOWN",
    "ERROR",
]


class ProducerHealth(BaseModel):
    producer_name: str
    neuron_name: str | None = None
    registered: bool = False
    expected: bool = False
    observed: bool = False
    signal_count: int = Field(default=0, ge=0)
    runtime_signal_count: int = Field(default=0, ge=0)
    dry_run_signal_count: int = Field(default=0, ge=0)
    recent_signal_count: int = Field(default=0, ge=0)
    stale_signal_count: int = Field(default=0, ge=0)
    brain_output_count: int = Field(default=0, ge=0)
    coordinator_decision_count: int = Field(default=0, ge=0)
    lineage_complete_count: int = Field(default=0, ge=0)
    lineage_unbound_count: int = Field(default=0, ge=0)
    avg_quality_score: float | None = None
    health_status: ProducerHealthStatus | str
    health_reason: str
    dry_run_only: bool = False
    runtime_active: bool = False
    silent_expected: bool = False
    degraded: bool = False
    missing: bool = False
    can_feed_brain: bool = False
    can_feed_paper: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    analyzed_at: datetime | None = None

    @field_validator("producer_name")
    @classmethod
    def normalize_producer_name(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            return "unknown"
        return normalized

    @field_validator("health_status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("health_status is required")
        return normalized

    @field_validator("health_reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("health_reason is required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProducerHealthSummary(BaseModel):
    mock_data: bool = False
    overall_status: str
    paper_ready: bool = False
    total_producers: int = Field(default=0, ge=0)
    registered_producers: int = Field(default=0, ge=0)
    observed_producers: int = Field(default=0, ge=0)
    runtime_active_producers: int = Field(default=0, ge=0)
    dry_run_only_producers: int = Field(default=0, ge=0)
    silent_expected_neurons: list[str] = Field(default_factory=list)
    missing_neurons: list[str] = Field(default_factory=list)
    degraded_neurons: list[str] = Field(default_factory=list)
    dry_run_only_neurons: list[str] = Field(default_factory=list)
    producer_health: list[ProducerHealth] = Field(default_factory=list)
    neuron_runtime_truth: dict[str, list[str]] = Field(default_factory=dict)
    last_updated: datetime
    analysis_status: str = "OK"

    @field_validator("overall_status", "analysis_status")
    @classmethod
    def normalize_summary_status(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("status is required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
