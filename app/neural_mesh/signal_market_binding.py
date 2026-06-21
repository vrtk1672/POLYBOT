from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


BindingCandidateAction = Literal[
    "AUTO_LINKED",
    "REVIEW_ONLY",
    "BLOCKED_WEAK_EVIDENCE",
    "BLOCKED_STALE",
    "BLOCKED_DRY_RUN",
    "BLOCKED_MISSING_MARKET",
    "BLOCKED_AMBIGUOUS",
    "ERROR",
]


class SignalMarketBindingCandidate(BaseModel):
    signal_id: str
    candidate_market_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)
    reason: str
    action: BindingCandidateAction | str
    created_at: datetime | None = None

    @field_validator("signal_id", "reason")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("signal binding candidate requires signal_id and reason")
        return normalized

    @field_validator("action")
    @classmethod
    def normalize_action(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("candidate action is required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SignalMarketBindingRun(BaseModel):
    mock_data: bool = False
    run_id: str
    status: str
    signals_checked: int = Field(default=0, ge=0)
    runtime_signals_checked: int = Field(default=0, ge=0)
    already_linked: int = Field(default=0, ge=0)
    safe_links_created: int = Field(default=0, ge=0)
    suggestions_created: int = Field(default=0, ge=0)
    remained_unlinked: int = Field(default=0, ge=0)
    stale_skipped: int = Field(default=0, ge=0)
    dry_run_skipped: int = Field(default=0, ge=0)
    weak_evidence_skipped: int = Field(default=0, ge=0)
    ambiguous_candidates: int = Field(default=0, ge=0)
    signal_market_links_before: int = Field(default=0, ge=0)
    signal_market_links_after: int = Field(default=0, ge=0)
    paper_ready_before: bool = False
    paper_ready_after: bool = False
    orders_created: int = 0
    order_intents_created: int = 0
    fills_created: int = 0
    positions_created: int = 0
    live_actions_created: int = 0
    candidates: list[SignalMarketBindingCandidate] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None

    @field_validator("run_id", "status")
    @classmethod
    def require_run_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("run_id and status are required")
        return normalized

    @model_validator(mode="after")
    def enforce_non_executing(self) -> "SignalMarketBindingRun":
        if self.mock_data:
            raise ValueError("market binding recovery cannot return mock data")
        if self.paper_ready_before or self.paper_ready_after:
            raise ValueError("market binding recovery must not mark Paper ready")
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
            raise ValueError("market binding recovery created executable artifacts")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

