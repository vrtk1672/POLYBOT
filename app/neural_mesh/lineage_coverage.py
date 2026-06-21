from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


LineageStatus = Literal[
    "COMPLETE",
    "PARTIAL",
    "UNBOUND",
    "DRY_RUN_ONLY",
    "RUNTIME_VERIFIED",
    "MANUAL",
    "ADAPTER",
    "STALE_OR_UNKNOWN",
    "ERROR",
]

UnboundReason = Literal[
    "MISSING_PRODUCER",
    "MISSING_SOURCE",
    "MISSING_CORRELATION_ID",
    "MISSING_RAW_PAYLOAD_REF",
    "MISSING_GENERATED_FROM",
    "MISSING_GENERATED_AT",
    "DRY_RUN_ONLY",
    "UNKNOWN_ORIGIN",
    "NO_EVENT_TRACE",
    "NO_PAYLOAD_TRACE",
    "NO_PRODUCER_TRACE",
    "ALREADY_BOUND",
    "UNKNOWN",
]

AnalysisStatus = Literal["OK", "PARTIAL", "ERROR"]


class SignalLineageCoverageAnalysis(BaseModel):
    signal_id: str
    lineage_status: LineageStatus | str
    lineage_trust_score: float = Field(ge=0, le=1)
    is_bound: bool = False
    is_unbound: bool = True
    primary_unbound_reason: UnboundReason | str
    unbound_reasons: list[str] = Field(default_factory=list)
    missing_lineage_fields: list[str] = Field(default_factory=list)
    producer: str | None = None
    source: str | None = None
    correlation_id: str | None = None
    raw_payload_ref: str | None = None
    generated_from: str | None = None
    generated_by: str | None = None
    generated_at: datetime | None = None
    signal_created_at: datetime | None = None
    is_dry_run_generated: bool = False
    is_runtime_generated: bool = False
    is_manual_generated: bool = False
    is_adapter_generated: bool = False
    has_producer: bool = False
    has_source: bool = False
    has_correlation_id: bool = False
    has_raw_payload_ref: bool = False
    has_generated_from: bool = False
    has_generated_at: bool = False
    has_explainable_origin: bool = False
    can_trace_to_event: bool = False
    can_trace_to_payload: bool = False
    can_trace_to_producer: bool = False
    can_feed_brain_by_lineage: bool = False
    can_feed_paper_by_lineage: bool = False
    analysis_status: AnalysisStatus | str = "OK"
    analysis_error: str | None = None
    analyzed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("signal_id")
    @classmethod
    def require_signal_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("signal_id is required")
        return normalized

    @field_validator("lineage_status", "primary_unbound_reason", "analysis_status")
    @classmethod
    def normalize_upper_text(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("lineage status/reason fields are required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["blocked_by"] = data.get("unbound_reasons", [])
        return data


def lineage_coverage_from_row(row: dict[str, Any]) -> SignalLineageCoverageAnalysis:
    data = dict(row)
    data["unbound_reasons"] = data.pop("unbound_reasons_json", []) or []
    data["missing_lineage_fields"] = data.pop("missing_lineage_fields_json", []) or []
    return SignalLineageCoverageAnalysis(**data)
