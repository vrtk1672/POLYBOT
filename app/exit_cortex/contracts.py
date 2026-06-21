from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


PlanStatus = Literal["ACTIVE", "PENDING_ORDER", "COMPLETED", "CANCELLED", "FAILED", "INSUFFICIENT_DATA"]
IntentStatus = Literal["CREATED", "READY_FOR_PAPER_EXECUTION", "READY_FOR_SHADOW_PLAN", "BLOCKED", "CANCELLED", "COMPLETED", "FAILED"]
ExitMode = Literal["PAPER_SIM_EXIT", "SHADOW_EXIT_PLAN"]


def non_negative(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(default if value is None else value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, number)


def bounded(value: float | int | None, default: float = 0.0) -> float:
    return max(0.0, min(1.0, non_negative(value, default)))


class ExitPlan(BaseModel):
    exit_plan_id: str = Field(default_factory=lambda: f"exit_plan_{uuid4().hex}")
    market_id: str
    market_family: str | None = None
    side: str = "YES"
    engine: str = "SAFE"
    strategy_route_id: int | None = None
    allocation_id: str | None = None
    risk_gate_run_id: str | None = None
    order_id: str | None = None
    position_ref: str | None = None
    entry_price: float
    entry_size: float
    target_exit: float | None = None
    partial_take_profit: float | None = None
    partial_take_profit_pct: float | None = None
    stop_loss: float | None = None
    max_hold_seconds: int | None = None
    invalidation_rule: dict[str, Any] = Field(default_factory=dict)
    liquidity_exit_check: dict[str, Any] = Field(default_factory=dict)
    emergency_exit: dict[str, Any] = Field(default_factory=dict)
    momentum_decay_exit: dict[str, Any] = Field(default_factory=dict)
    spread_exit: dict[str, Any] = Field(default_factory=dict)
    news_invalidated_exit: dict[str, Any] = Field(default_factory=dict)
    exit_mode: ExitMode = "PAPER_SIM_EXIT"
    plan_status: PlanStatus = "ACTIVE"
    created_from: str = "exit_cortex_v2"
    data_confidence: float = 0.0
    insufficient_data: bool = False
    insufficient_data_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize(self) -> "ExitPlan":
        self.side = str(self.side or "YES").upper()
        self.engine = str(self.engine or "SAFE").upper()
        self.entry_price = non_negative(self.entry_price)
        self.entry_size = non_negative(self.entry_size)
        self.target_exit = None if self.target_exit is None else non_negative(self.target_exit)
        self.partial_take_profit = None if self.partial_take_profit is None else non_negative(self.partial_take_profit)
        self.partial_take_profit_pct = None if self.partial_take_profit_pct is None else bounded(self.partial_take_profit_pct)
        self.stop_loss = None if self.stop_loss is None else non_negative(self.stop_loss)
        self.max_hold_seconds = None if self.max_hold_seconds is None else int(non_negative(self.max_hold_seconds))
        self.data_confidence = bounded(self.data_confidence)
        self.insufficient_data_reasons = list(dict.fromkeys(str(item) for item in self.insufficient_data_reasons))
        if self.insufficient_data:
            self.plan_status = "INSUFFICIENT_DATA"
        return self


class ExitTrigger(BaseModel):
    trigger_type: str
    triggered: bool = False
    severity: str = "INFO"
    reason: str = ""
    current_price: float | None = None
    threshold: float | None = None
    confidence: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)


class ExitIntent(BaseModel):
    exit_intent_id: str = Field(default_factory=lambda: f"exit_intent_{uuid4().hex}")
    exit_plan_id: str
    order_id: str | None = None
    market_id: str
    side: str = "YES"
    exit_side: str = "SELL"
    reason: str
    intent_status: IntentStatus = "CREATED"
    exit_price_target: float | None = None
    exit_size: float
    exit_size_pct: float | None = None
    max_slippage_bps: float = 150.0
    urgency: str = "NORMAL"
    execution_mode: ExitMode = "PAPER_SIM_EXIT"
    paper_shadow_only: bool = True
    risk_snapshot: dict[str, Any] = Field(default_factory=dict)
    liquidity_snapshot: dict[str, Any] = Field(default_factory=dict)
    trigger_snapshot: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self) -> "ExitIntent":
        self.side = str(self.side or "YES").upper()
        self.exit_side = "SELL"
        self.exit_size = non_negative(self.exit_size)
        self.exit_size_pct = None if self.exit_size_pct is None else bounded(self.exit_size_pct)
        self.max_slippage_bps = non_negative(self.max_slippage_bps, 150.0)
        self.paper_shadow_only = True
        return self


class ExitDecision(BaseModel):
    exit_plan_id: str
    should_exit: bool = False
    triggers: list[ExitTrigger] = Field(default_factory=list)
    selected_reason: str | None = None
    exit_intent: ExitIntent | None = None
    blocked_reasons: list[str] = Field(default_factory=list)
    explanation: str = ""


class ExitQualityResult(BaseModel):
    quality_id: str = Field(default_factory=lambda: f"exit_quality_{uuid4().hex}")
    exit_plan_id: str
    exit_intent_id: str | None = None
    order_id: str | None = None
    market_id: str
    expected_exit_price: float
    actual_exit_price: float | None = None
    expected_slippage_bps: float = 0.0
    actual_slippage_bps: float | None = None
    expected_exit_liquidity_score: float = 0.0
    actual_exit_fill_ratio: float | None = None
    exit_latency_ms: float | None = None
    exit_quality_score: float = 0.0
    quality_flags: list[str] = Field(default_factory=list)


class ExitFailure(BaseModel):
    failure_id: str = Field(default_factory=lambda: f"exit_failure_{uuid4().hex}")
    exit_plan_id: str | None = None
    exit_intent_id: str | None = None
    order_id: str | None = None
    market_id: str | None = None
    failure_type: str
    severity: str = "WARNING"
    reason: str
    recoverable: bool = True
    details: dict[str, Any] = Field(default_factory=dict)


def now_utc() -> datetime:
    return datetime.now(UTC)

