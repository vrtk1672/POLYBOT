from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


RuntimeEvidenceStatus = Literal["OK", "DEGRADED", "DRY_RUN", "ERROR"]


class RuntimeProducerEvidenceItem(BaseModel):
    signal_id: str | None = None
    producer_name: str
    source: str
    correlation_id: str
    raw_payload_ref: str
    generated_from: str = "source_status"
    generated_by: Literal["runtime"] = "runtime"
    is_runtime_generated: bool = True
    is_dry_run_generated: bool = False
    status: Literal["OK", "PLANNED", "ERROR"] = "OK"
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    @field_validator("producer_name", "source", "correlation_id", "raw_payload_ref", "generated_from")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("runtime evidence metadata field is required")
        return normalized

    @model_validator(mode="after")
    def enforce_runtime_only(self) -> "RuntimeProducerEvidenceItem":
        if not self.is_runtime_generated or self.is_dry_run_generated:
            raise ValueError("runtime evidence item must be runtime-generated and non-dry-run")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RuntimeProducerEvidenceRun(BaseModel):
    mock_data: bool = False
    run_id: str
    status: RuntimeEvidenceStatus = "OK"
    producers_checked: int = Field(default=0, ge=0)
    runtime_producers_active_before: int = Field(default=0, ge=0)
    runtime_producers_active_after: int = Field(default=0, ge=0)
    dry_run_only_producers_before: int = Field(default=0, ge=0)
    dry_run_only_producers_after: int = Field(default=0, ge=0)
    signals_created: int = Field(default=0, ge=0)
    signals_updated: int = Field(default=0, ge=0)
    quality_updated: int = Field(default=0, ge=0)
    processing_updated: int = Field(default=0, ge=0)
    lineage_updated: int = Field(default=0, ge=0)
    link_coverage_updated: int = Field(default=0, ge=0)
    provenance_updated: int = Field(default=0, ge=0)
    producer_health_updated: bool = False
    mesh_blockers_updated: bool = False
    paper_ready_before: bool = False
    paper_ready_after: bool = False
    orders_created: int = 0
    order_intents_created: int = 0
    live_actions_created: int = 0
    blocked_by: list[str] = Field(default_factory=list)
    remaining_blockers: list[str] = Field(default_factory=list)
    items: list[RuntimeProducerEvidenceItem] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_summary: str | None = None

    @model_validator(mode="after")
    def enforce_non_executing(self) -> "RuntimeProducerEvidenceRun":
        if self.paper_ready_before or self.paper_ready_after:
            raise ValueError("runtime producer evidence cannot mark paper_ready true")
        if self.orders_created or self.order_intents_created or self.live_actions_created:
            raise ValueError("runtime producer evidence cannot create executable artifacts")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def runtime_evidence_run_from_row(row: dict[str, Any]) -> RuntimeProducerEvidenceRun:
    return RuntimeProducerEvidenceRun(
        run_id=str(row["run_id"]),
        status=row.get("status") or "OK",
        producers_checked=int(row.get("producers_checked") or 0),
        runtime_producers_active_before=int(row.get("runtime_producers_active_before") or 0),
        runtime_producers_active_after=int(row.get("runtime_producers_active_after") or 0),
        dry_run_only_producers_before=int(row.get("dry_run_only_producers_before") or 0),
        dry_run_only_producers_after=int(row.get("dry_run_only_producers_after") or 0),
        signals_created=int(row.get("signals_created") or 0),
        signals_updated=int(row.get("signals_updated") or 0),
        quality_updated=int(row.get("quality_updated") or 0),
        processing_updated=int(row.get("processing_updated") or 0),
        lineage_updated=int(row.get("lineage_updated") or 0),
        link_coverage_updated=int(row.get("link_coverage_updated") or 0),
        provenance_updated=int(row.get("provenance_updated") or 0),
        producer_health_updated=bool(row.get("producer_health_updated")),
        mesh_blockers_updated=bool(row.get("mesh_blockers_updated")),
        paper_ready_before=bool(row.get("paper_ready_before")),
        paper_ready_after=bool(row.get("paper_ready_after")),
        orders_created=int(row.get("orders_created") or 0),
        order_intents_created=int(row.get("order_intents_created") or 0),
        live_actions_created=int(row.get("live_actions_created") or 0),
        blocked_by=list(row.get("blocked_by") or []),
        remaining_blockers=list(row.get("remaining_blockers") or []),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        error_summary=row.get("error_summary"),
    )
