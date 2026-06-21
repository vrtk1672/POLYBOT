from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class RuntimeCoordinatorInput(BaseModel):
    brain_output_id: str
    source_signal_ids: list[str] = Field(default_factory=list)
    brain_confidence: float | None = Field(default=None, ge=0, le=1)
    brain_decision_type: str | None = None
    coordinator_decision_type: str
    blockers: list[str] = Field(default_factory=list)
    paper_allowed: bool = False
    execution_allowed: bool = False
    order_intent_allowed: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_non_executing(self) -> "RuntimeCoordinatorInput":
        if self.paper_allowed or self.execution_allowed or self.order_intent_allowed:
            raise ValueError("runtime coordinator inputs must remain non-executing")
        return self


class RuntimeCoordinatorRun(BaseModel):
    mock_data: bool = False
    run_id: str
    status: str
    input_runtime_brain_outputs: int = Field(default=0, ge=0)
    eligible_brain_outputs: int = Field(default=0, ge=0)
    coordinator_decisions_created: int = Field(default=0, ge=0)
    coordinator_decisions_updated: int = Field(default=0, ge=0)
    dry_run_decisions_touched: int = 0
    runtime_coordinator_decisions_before: int = Field(default=0, ge=0)
    runtime_coordinator_decisions_after: int = Field(default=0, ge=0)
    dry_run_coordinator_decisions: int = Field(default=0, ge=0)
    runtime_brain_outputs: int = Field(default=0, ge=0)
    dry_run_brain_outputs: int = Field(default=0, ge=0)
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
    inputs: list[RuntimeCoordinatorInput] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None

    @model_validator(mode="after")
    def enforce_non_executing(self) -> "RuntimeCoordinatorRun":
        if self.mock_data:
            raise ValueError("runtime coordinator run cannot be mock data")
        if self.paper_ready_before or self.paper_ready_after:
            raise ValueError("runtime coordinator run must not mark Paper ready")
        if self.dry_run_decisions_touched:
            raise ValueError("runtime coordinator run must not mutate dry-run decisions")
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
            raise ValueError("runtime coordinator run created executable artifacts")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
