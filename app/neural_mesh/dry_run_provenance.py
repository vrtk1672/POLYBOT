from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ObjectType = Literal[
    "SIGNAL",
    "BRAIN_OUTPUT",
    "COORDINATOR_DECISION",
    "QUALITY_EVALUATION",
    "PROCESSING_STATE",
    "LINK_COVERAGE",
    "LINEAGE_COVERAGE",
]

GeneratedBy = Literal["dry_run", "runtime", "adapter", "manual", "unknown"]
ProvenanceStatus = Literal["RUNTIME_VERIFIED", "DRY_RUN_ONLY", "ADAPTER_GENERATED", "MANUAL_GENERATED", "UNKNOWN", "MIXED", "ERROR"]


class DryRunProvenanceAnalysis(BaseModel):
    object_type: ObjectType | str
    object_id: str
    generated_by: GeneratedBy | str
    dry_run_id: str | None = None
    producer_name: str | None = None
    is_dry_run_generated: bool = False
    is_runtime_generated: bool = False
    is_adapter_generated: bool = False
    is_manual_generated: bool = False
    provenance_status: ProvenanceStatus | str
    provenance_confidence: float = Field(ge=0, le=1)
    provenance_reason: str | None = None
    can_feed_brain_by_provenance: bool = False
    can_feed_paper_by_provenance: bool = False
    source_table: str | None = None
    source_created_at: datetime | None = None
    analyzed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("object_type", "provenance_status")
    @classmethod
    def normalize_upper(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("object_type and provenance_status are required")
        return normalized

    @field_validator("generated_by")
    @classmethod
    def normalize_generated_by(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("generated_by is required")
        return normalized

    @field_validator("object_id")
    @classmethod
    def require_object_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("object_id is required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def dry_run_provenance_from_row(row: dict[str, Any]) -> DryRunProvenanceAnalysis:
    return DryRunProvenanceAnalysis(**dict(row))
