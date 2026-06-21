from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


RuntimeBrainStatus = Literal["OK", "DEGRADED", "DRY_RUN", "ERROR"]
RuntimeBrainDecisionType = Literal["OBSERVE", "WEAK_SIGNAL", "NO_TRADE_CANDIDATE"]


class RuntimeBrainInput(BaseModel):
    signal_id: str
    signal_quality_score: float | None = Field(default=None, ge=0, le=1)
    signal_processing_state: str | None = None
    lineage_status: str | None = None
    link_status: str | None = None
    decision_type: RuntimeBrainDecisionType
    blockers: list[str] = Field(default_factory=list)
    paper_allowed: bool = False
    execution_allowed: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_non_executing(self) -> "RuntimeBrainInput":
        if self.paper_allowed or self.execution_allowed:
            raise ValueError("runtime brain inputs cannot allow paper or execution")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RuntimeBrainProducerRun(BaseModel):
    mock_data: bool = False
    run_id: str
    status: RuntimeBrainStatus = "OK"
    input_runtime_signals: int = Field(default=0, ge=0)
    eligible_signals: int = Field(default=0, ge=0)
    brain_outputs_created: int = Field(default=0, ge=0)
    brain_outputs_updated: int = Field(default=0, ge=0)
    dry_run_outputs_touched: int = 0
    runtime_brain_outputs_before: int = Field(default=0, ge=0)
    runtime_brain_outputs_after: int = Field(default=0, ge=0)
    dry_run_brain_outputs: int = Field(default=0, ge=0)
    coordinator_runtime_decisions: int = Field(default=0, ge=0)
    provenance_updated: int = Field(default=0, ge=0)
    producer_health_updated: bool = False
    mesh_blockers_updated: bool = False
    paper_ready_before: bool = False
    paper_ready_after: bool = False
    orders_created: int = 0
    order_intents_created: int = 0
    fills_created: int = 0
    positions_created: int = 0
    live_actions_created: int = 0
    remaining_blockers: list[str] = Field(default_factory=list)
    inputs: list[RuntimeBrainInput] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_summary: str | None = None

    @model_validator(mode="after")
    def enforce_non_executing(self) -> "RuntimeBrainProducerRun":
        if self.paper_ready_before or self.paper_ready_after:
            raise ValueError("runtime brain producer cannot mark paper_ready true")
        if any(
            count
            for count in (
                self.orders_created,
                self.order_intents_created,
                self.fills_created,
                self.positions_created,
                self.live_actions_created,
                self.coordinator_runtime_decisions,
                self.dry_run_outputs_touched,
            )
        ):
            raise ValueError("runtime brain producer cannot create execution artifacts, coordinator decisions, or mutate dry-run outputs")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
