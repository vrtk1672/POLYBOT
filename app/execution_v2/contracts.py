from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


ExecutionMode = Literal["PAPER_SIM", "SHADOW_PLAN"]
OrderStatus = Literal["CREATED", "SUBMITTED_PAPER", "PLANNED_SHADOW", "PARTIALLY_FILLED", "FILLED", "FAILED", "CANCELLED", "EXPIRED", "BLOCKED"]
FillMode = Literal["PAPER_SIM", "SHADOW_ESTIMATE"]
FillStatus = Literal["FILLED", "PARTIAL", "FAILED", "ESTIMATED"]


def non_negative(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(default if value is None else value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, number)


def bounded(value: float | int | None, default: float = 0.0) -> float:
    return max(0.0, min(1.0, non_negative(value, default)))


class OrderContract(BaseModel):
    order_id: str = Field(default_factory=lambda: f"order_v2_{uuid4().hex}")
    market_id: str
    market_family: str | None = None
    side: str = "YES"
    token_id: str | None = None
    engine: str = "SAFE"
    order_type: str = "LIMIT"
    execution_mode: ExecutionMode = "PAPER_SIM"
    price: float
    size: float
    size_usd: float
    ttl_seconds: int = 300
    max_slippage_bps: float = 150.0
    cancel_if: dict[str, Any] = Field(default_factory=dict)
    risk_gate_run_id: str | None = None
    risk_decision_id: int | None = None
    exit_plan_id: str
    strategy_route_id: int | None = None
    allocation_id: str | None = None
    orderbook_snapshot: dict[str, Any] = Field(default_factory=dict)
    liquidity_snapshot: dict[str, Any] = Field(default_factory=dict)
    fee_snapshot: dict[str, Any] = Field(default_factory=dict)
    risk_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_from: str = "execution_v2"
    dry_run: bool = False

    @model_validator(mode="after")
    def normalize(self) -> "OrderContract":
        self.side = str(self.side or "YES").upper()
        self.engine = str(self.engine or "SAFE").upper()
        self.order_type = "LIMIT"
        self.price = non_negative(self.price)
        self.size = non_negative(self.size)
        self.size_usd = non_negative(self.size_usd)
        self.max_slippage_bps = non_negative(self.max_slippage_bps, 150.0)
        self.ttl_seconds = int(non_negative(self.ttl_seconds, 300))
        return self


class ExecutionPrecheck(BaseModel):
    has_strategy_route: bool = False
    has_capital_allocation: bool = False
    has_risk_approval: bool = False
    has_exit_plan: bool = False
    governor_ok: bool = False
    has_bid_ask: bool = False
    has_depth: bool = False
    slippage_ok: bool = False
    execution_mode_allowed: bool = False
    block_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return not self.block_reasons


class FillRecord(BaseModel):
    fill_id: str = Field(default_factory=lambda: f"fill_v2_{uuid4().hex}")
    order_id: str
    market_id: str
    side: str
    fill_mode: FillMode
    fill_status: FillStatus
    requested_size: float
    filled_size: float
    fill_price: float
    expected_price: float
    slippage_bps: float
    fee_bps: float = 0.0
    fee_usd: float = 0.0
    fill_probability: float = 0.0
    liquidity_consumed: dict[str, Any] = Field(default_factory=dict)
    partial: bool = False
    failed_reason: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "FillRecord":
        self.requested_size = non_negative(self.requested_size)
        self.filled_size = min(non_negative(self.filled_size), self.requested_size)
        self.fill_price = non_negative(self.fill_price)
        self.expected_price = non_negative(self.expected_price)
        self.slippage_bps = non_negative(self.slippage_bps)
        self.fee_bps = non_negative(self.fee_bps)
        self.fee_usd = non_negative(self.fee_usd)
        self.fill_probability = bounded(self.fill_probability)
        self.partial = self.fill_status == "PARTIAL" or (0 < self.filled_size < self.requested_size)
        return self


class PaperExecutionResult(BaseModel):
    order_id: str
    order_status: OrderStatus
    fills: list[FillRecord] = Field(default_factory=list)
    filled_size: float = 0.0
    remaining_size: float = 0.0
    avg_fill_price: float | None = None
    slippage_bps: float = 0.0
    fees_usd: float = 0.0
    quality_score: float = 0.0


class ShadowExecutionPlan(BaseModel):
    order_id: str
    planned_order: dict[str, Any]
    expected_fill_probability: float
    expected_slippage_bps: float
    expected_latency_ms: float
    cancel_conditions: dict[str, Any]
    not_sent_reason: str = "shadow_plan_only_no_external_send"


class ExecutionQualityResult(BaseModel):
    quality_id: str = Field(default_factory=lambda: f"execution_quality_{uuid4().hex}")
    order_id: str
    market_id: str
    expected_fill_price: float
    actual_fill_price: float | None = None
    expected_slippage_bps: float = 0.0
    actual_slippage_bps: float | None = None
    expected_fill_probability: float = 0.0
    actual_fill_ratio: float = 0.0
    cancel_count: int = 0
    failed_fill_count: int = 0
    partial_fill_count: int = 0
    execution_quality_score: float = 0.0
    quality_flags: list[str] = Field(default_factory=list)


class ExecutionOrderState(BaseModel):
    order_id: str
    order_status: OrderStatus
    filled_size: float = 0.0
    remaining_size: float = 0.0
    avg_fill_price: float | None = None


def expires_at(ttl_seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=max(0, int(ttl_seconds)))


def reproducibility_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

