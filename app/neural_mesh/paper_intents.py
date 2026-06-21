from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PaperIntentStatus = Literal["CREATED", "BLOCKED", "CANCELLED", "ERROR"]
PaperIntentType = Literal["PAPER_ENTRY_INTENT", "PAPER_NO_TRADE_INTENT_PLACEHOLDER"]
NoTradeCategory = Literal[
    "RISK_BLOCKED",
    "EXIT_BLOCKED",
    "ELIGIBILITY_BLOCKED",
    "MISSING_EVIDENCE",
    "STALE_DATA",
    "WEAK_LINEAGE",
    "DRY_RUN_ONLY",
    "NO_ELIGIBLE_CANDIDATE",
    "ERROR",
]


class PaperIntent(BaseModel):
    paper_intent_id: str
    eligibility_id: str
    thesis_id: str
    risk_decision_id: str
    exit_plan_id: str
    coordinator_decision_id: str | None = None
    market_id: str
    side: str
    price_basis: str = "ORDERBOOK_MID"
    orderbook_snapshot_id: int | None = None
    intended_price: float | None = None
    max_slippage: float | None = 0.02
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    intent_status: PaperIntentStatus | str = "CREATED"
    intent_type: PaperIntentType | str = "PAPER_ENTRY_INTENT"
    intent_reason: str = "Fully eligible Paper candidate reached the non-executing Paper Intent Gate."
    evidence: dict[str, Any] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    paper_only: bool = True
    live: bool = False
    execution_allowed: bool = False
    order_intent_created: bool = False
    generated_by: str = "runtime"
    producer_name: str = "paper_intent_gate"
    is_runtime_generated: bool = True
    is_dry_run_generated: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("paper_intent_id", "eligibility_id", "thesis_id", "risk_decision_id", "exit_plan_id", "market_id", "side")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Paper Intent requires eligibility, thesis, risk, exit, market, and side identifiers")
        return normalized

    @field_validator("side", "intent_status", "intent_type")
    @classmethod
    def uppercase_text(cls, value: str) -> str:
        return str(value or "").strip().upper()

    @field_validator("blockers")
    @classmethod
    def clean_blockers(cls, value: list[str]) -> list[str]:
        return sorted({str(item).strip().upper() for item in value or [] if str(item).strip()})

    @model_validator(mode="after")
    def enforce_non_executing_intent(self) -> "PaperIntent":
        if not self.paper_only:
            raise ValueError("Paper Intent must remain paper_only=true")
        if self.live:
            raise ValueError("Paper Intent must remain live=false")
        if self.execution_allowed:
            raise ValueError("Paper Intent must not allow execution")
        if self.order_intent_created:
            raise ValueError("Paper Intent must not create order intents")
        if self.intent_status == "CREATED" and self.blockers:
            raise ValueError("Created Paper Intent cannot carry hard blockers")
        if self.is_dry_run_generated:
            raise ValueError("Paper Intent cannot be generated from dry-run evidence")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class NoTradeLedgerRecord(BaseModel):
    no_trade_id: str
    eligibility_id: str | None = None
    thesis_id: str | None = None
    risk_decision_id: str | None = None
    exit_plan_id: str | None = None
    market_id: str | None = None
    side: str | None = None
    no_trade_reason: str
    no_trade_category: NoTradeCategory | str
    blockers: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    source_status: str | None = None
    source_layer: str = "paper_intent_gate"
    generated_by: str = "runtime"
    producer_name: str = "no_trade_ledger"
    is_runtime_generated: bool = True
    is_dry_run_generated: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("no_trade_id", "no_trade_reason", "no_trade_category", "source_layer")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("No-Trade ledger record requires id, reason, category, and source layer")
        return normalized

    @field_validator("side", "source_status")
    @classmethod
    def uppercase_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().upper()
        return normalized or None

    @field_validator("no_trade_category")
    @classmethod
    def uppercase_category(cls, value: str) -> str:
        return str(value or "").strip().upper()

    @field_validator("blockers", "missing_requirements")
    @classmethod
    def clean_codes(cls, value: list[str]) -> list[str]:
        return sorted({str(item).strip().upper() for item in value or [] if str(item).strip()})

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PaperIntentRun(BaseModel):
    mock_data: bool = False
    run_id: str
    status: str
    candidates_checked: int = Field(default=0, ge=0)
    eligible_candidates: int = Field(default=0, ge=0)
    paper_intents_created: int = Field(default=0, ge=0)
    paper_intents_updated: int = Field(default=0, ge=0)
    no_trade_records_created: int = Field(default=0, ge=0)
    no_trade_records_updated: int = Field(default=0, ge=0)
    blocked_candidates: int = Field(default=0, ge=0)
    missing_eligibility_count: int = Field(default=0, ge=0)
    accounted_candidates: int = Field(default=0, ge=0)
    unaccounted_candidates: int = Field(default=0, ge=0)
    paper_ready_before: bool = False
    paper_ready_after: bool = False
    orders_created: int = 0
    order_intents_created: int = 0
    fills_created: int = 0
    positions_created: int = 0
    live_actions_created: int = 0
    started_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None
    paper_intents: list[PaperIntent] = Field(default_factory=list)
    no_trade_records: list[NoTradeLedgerRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_non_executing_run(self) -> "PaperIntentRun":
        if self.mock_data:
            raise ValueError("Paper Intent run cannot return mock data")
        if self.paper_ready_before or self.paper_ready_after:
            raise ValueError("Paper Intent run must not mark Paper ready")
        if any(
            value != 0
            for value in (
                self.order_intents_created,
                self.fills_created,
                self.positions_created,
                self.live_actions_created,
            )
        ):
            raise ValueError("Paper Intent run created executable artifacts")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
