from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


EngineName = Literal["SAFE", "STRIKE", "CONVEX", "MAKER", "HUNT", "MOONSHOT_BASKET", "REINVEST", "NO_TRADE"]
CapitalBucket = Literal[
    "SURVIVAL_RESERVE",
    "SAFE_CAPITAL",
    "STRIKE_CAPITAL",
    "CONVEX_CAPITAL",
    "MAKER_CAPITAL",
    "HUNT_CAPITAL",
    "MOONSHOT_BASKET",
    "CASH_RESERVE",
    "ATTACK_BANK",
    "PROFIT_POCKET",
]
AllocationStatus = Literal["ALLOCATED", "BLOCKED", "REDUCED", "INSUFFICIENT_DATA", "DRY_RUN"]


def non_negative(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(default if value is None else value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, number)


def bounded(value: float | int | None, default: float = 0.0) -> float:
    return max(0.0, min(1.0, non_negative(value, default)))


class CapitalState(BaseModel):
    state_id: str = Field(default_factory=lambda: f"capital_state_{uuid.uuid4().hex}")
    runtime_mode: str | None = None
    total_capital_usd: float = 0.0
    base_capital_usd: float = 0.0
    available_capital_usd: float = 0.0
    locked_capital_usd: float = 0.0
    open_exposure_usd: float = 0.0
    survival_reserve_usd: float = 0.0
    cash_reserve_usd: float = 0.0
    profit_pocket_usd: float = 0.0
    attack_bank_usd: float = 0.0
    realized_pnl_usd: float = 0.0
    unrealized_pnl_usd: float | None = None
    daily_pnl_usd: float | None = None
    weekly_pnl_usd: float | None = None
    loss_streak_count: int = 0
    win_streak_count: int = 0
    source_type: str = "UNKNOWN"
    source_ref: str | None = None
    data_confidence: float = 0.0
    insufficient_data: bool = False
    insufficient_data_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def normalize(self) -> "CapitalState":
        for field in (
            "total_capital_usd",
            "base_capital_usd",
            "available_capital_usd",
            "locked_capital_usd",
            "open_exposure_usd",
            "survival_reserve_usd",
            "cash_reserve_usd",
            "profit_pocket_usd",
            "attack_bank_usd",
            "realized_pnl_usd",
        ):
            setattr(self, field, non_negative(getattr(self, field)))
        self.loss_streak_count = int(non_negative(self.loss_streak_count))
        self.win_streak_count = int(non_negative(self.win_streak_count))
        self.data_confidence = bounded(self.data_confidence)
        self.insufficient_data_reasons = list(dict.fromkeys(str(item) for item in self.insufficient_data_reasons))
        if self.total_capital_usd <= 0 or self.available_capital_usd < 0:
            self.insufficient_data = True
            if "missing_capital_data" not in self.insufficient_data_reasons:
                self.insufficient_data_reasons.append("missing_capital_data")
        return self


class EngineBudget(BaseModel):
    engine: EngineName
    bucket: CapitalBucket
    budget_usd: float = 0.0
    used_usd: float = 0.0
    reserved_usd: float = 0.0
    available_usd: float = 0.0
    max_position_usd: float = 0.0
    max_loss_usd: float = 0.0
    max_open_allocations: int = 1
    cooldown_active: bool = False
    loss_streak_multiplier: float = 1.0
    enabled: bool = True
    policy: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self) -> "EngineBudget":
        self.engine = str(self.engine).upper()  # type: ignore[assignment]
        self.bucket = str(self.bucket).upper()  # type: ignore[assignment]
        for field in ("budget_usd", "used_usd", "reserved_usd", "available_usd", "max_position_usd", "max_loss_usd"):
            setattr(self, field, non_negative(getattr(self, field)))
        if self.available_usd <= 0 and self.budget_usd > 0:
            self.available_usd = max(self.budget_usd - self.used_usd - self.reserved_usd, 0.0)
        self.loss_streak_multiplier = bounded(self.loss_streak_multiplier, 1.0)
        return self


class CapitalAllocationRequest(BaseModel):
    market_id: str
    side: str = "UNKNOWN"
    engine: EngineName
    strategy_route_id: int | None = None
    strategy_run_id: str | None = None
    requested_size_usd: float = 0.0
    max_loss_usd: float = 0.0
    expected_hold_minutes: int = 0
    route_confidence: float = 0.0
    route_status: str = "UNKNOWN"
    market_family: str | None = None
    dry_run: bool = False
    route: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self) -> "CapitalAllocationRequest":
        self.side = str(self.side or "UNKNOWN").upper()
        if self.side not in {"YES", "NO", "UNKNOWN"}:
            raise ValueError("invalid allocation side")
        self.engine = str(self.engine).upper()  # type: ignore[assignment]
        self.requested_size_usd = non_negative(self.requested_size_usd)
        self.max_loss_usd = non_negative(self.max_loss_usd)
        self.expected_hold_minutes = int(non_negative(self.expected_hold_minutes))
        self.route_confidence = bounded(self.route_confidence)
        self.route_status = str(self.route_status or "UNKNOWN").upper()
        return self


class CapitalAllocationDecision(BaseModel):
    allocation_id: str = Field(default_factory=lambda: f"allocation_{uuid.uuid4().hex}")
    market_id: str
    market_family: str | None = None
    side: str = "UNKNOWN"
    engine: EngineName
    bucket: CapitalBucket | None = None
    allocation_status: AllocationStatus
    requested_size_usd: float = 0.0
    approved_size_usd: float = 0.0
    max_loss_usd: float = 0.0
    reserve_after_usd: float = 0.0
    engine_budget_before_usd: float = 0.0
    engine_budget_after_usd: float = 0.0
    attack_bank_used_usd: float = 0.0
    profit_pocket_used_usd: float = 0.0
    base_capital_used_usd: float = 0.0
    allocation_reason: str = ""
    rejection_reason: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    strategy_route_id: int | None = None
    strategy_run_id: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "CapitalAllocationDecision":
        for field in (
            "requested_size_usd",
            "approved_size_usd",
            "max_loss_usd",
            "reserve_after_usd",
            "engine_budget_before_usd",
            "engine_budget_after_usd",
            "attack_bank_used_usd",
            "profit_pocket_used_usd",
            "base_capital_used_usd",
        ):
            setattr(self, field, non_negative(getattr(self, field)))
        if self.dry_run:
            self.allocation_status = "DRY_RUN"
        if self.engine == "NO_TRADE":
            self.approved_size_usd = 0.0
            self.bucket = None
        return self


class ReinvestDecision(BaseModel):
    event_type: str
    amount_usd: float = 0.0
    from_bucket: CapitalBucket | None = None
    to_bucket: CapitalBucket | None = None
    reason: str = ""
    allowed: bool = False
    block_reason: str | None = None
    dry_run: bool = False
    policy: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self) -> "ReinvestDecision":
        self.amount_usd = non_negative(self.amount_usd)
        if self.amount_usd <= 0:
            self.allowed = False
            self.block_reason = self.block_reason or "no_realized_profit"
        return self

