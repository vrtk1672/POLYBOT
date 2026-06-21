from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def bounded(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(default if value is None else value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def non_negative(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(default if value is None else value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, number)


class TechnicalSide(StrEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class TrendDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"
    UNKNOWN = "UNKNOWN"


class MarketRegime(StrEnum):
    QUIET = "quiet"
    TRENDING = "trending"
    VOLATILE = "volatile"
    ILLIQUID = "illiquid"
    STALE = "stale"
    CLOSING_SOON = "closing_soon"
    CHAOTIC = "chaotic"
    UNKNOWN = "unknown"


class MarketTechnicalSignal(BaseModel):
    market_id: str
    price_yes: float | None = None
    price_no: float | None = None
    price_change_1m: float = 0.0
    price_change_5m: float = 0.0
    price_change_15m: float = 0.0
    price_change_1h: float = 0.0
    volume_1h: float = 0.0
    volume_24h: float = 0.0
    volatility_score: float = 0.0
    momentum_score: float = 0.0
    trend_direction: TrendDirection = TrendDirection.UNKNOWN
    trend_strength: float = 0.0
    candle_summary: dict[str, Any] = Field(default_factory=dict)
    market_regime: MarketRegime = MarketRegime.UNKNOWN
    data_completeness_score: float = 0.0
    stale: bool = False
    source: str = "v2.8"
    raw_snapshot: dict[str, Any] = Field(default_factory=dict)
    block_reason: str | None = None

    @model_validator(mode="after")
    def bound_scores(self) -> "MarketTechnicalSignal":
        for field in ("volatility_score", "momentum_score", "trend_strength", "data_completeness_score"):
            setattr(self, field, bounded(getattr(self, field)))
        self.volume_1h = non_negative(self.volume_1h)
        self.volume_24h = non_negative(self.volume_24h)
        return self


class OrderbookSignal(BaseModel):
    market_id: str
    token_id: str | None = None
    side: TechnicalSide = TechnicalSide.UNKNOWN
    best_bid: float | None = None
    best_ask: float | None = None
    mid_price: float | None = None
    spread: float | None = None
    spread_bps: float | None = None
    depth_1c: float = 0.0
    depth_2c: float = 0.0
    depth_5c: float = 0.0
    bid_depth_total: float = 0.0
    ask_depth_total: float = 0.0
    imbalance_score: float = 0.5
    queue_quality_score: float = 0.0
    cancel_burst_score: float = 0.0
    microstructure_score: float = 0.0
    orderbook_quality_score: float = 0.0
    has_bid_ask: bool = False
    stale: bool = False
    source: str = "v2.8"
    raw_orderbook: dict[str, Any] = Field(default_factory=dict)
    block_reason: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "OrderbookSignal":
        for field in ("depth_1c", "depth_2c", "depth_5c", "bid_depth_total", "ask_depth_total"):
            setattr(self, field, non_negative(getattr(self, field)))
        for field in ("imbalance_score", "queue_quality_score", "cancel_burst_score", "microstructure_score", "orderbook_quality_score"):
            setattr(self, field, bounded(getattr(self, field), 0.5 if field == "imbalance_score" else 0.0))
        if self.spread_bps is not None:
            self.spread_bps = non_negative(self.spread_bps)
        return self


class LiquiditySignal(BaseModel):
    market_id: str
    token_id: str | None = None
    side: TechnicalSide = TechnicalSide.UNKNOWN
    expected_fill_score: float = 0.0
    expected_slippage_bps: float = 0.0
    expected_slippage_usd: float = 0.0
    exit_quality_score: float = 0.0
    max_safe_size_usd: float = 0.0
    max_safe_size_contracts: float = 0.0
    liquidity_decay_score: float = 0.0
    entry_liquidity_score: float = 0.0
    exit_liquidity_score: float = 0.0
    source: str = "v2.8"
    raw_liquidity: dict[str, Any] = Field(default_factory=dict)
    block_reason: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "LiquiditySignal":
        for field in ("expected_fill_score", "exit_quality_score", "liquidity_decay_score", "entry_liquidity_score", "exit_liquidity_score"):
            setattr(self, field, bounded(getattr(self, field)))
        for field in ("expected_slippage_bps", "expected_slippage_usd", "max_safe_size_usd", "max_safe_size_contracts"):
            setattr(self, field, non_negative(getattr(self, field)))
        return self


class TimeSignal(BaseModel):
    market_id: str
    market_close_time: datetime | None = None
    time_to_close_seconds: int | None = None
    expected_hold_seconds: int = 0
    lockup_penalty_score: float = 0.0
    urgency_score: float = 0.0
    roi_per_hour_reference: float | None = None
    time_efficiency_score: float = 0.0
    ttl_bucket: str = "unknown"
    source: str = "v2.8"
    block_reason: str | None = None

    @field_validator("time_to_close_seconds", "expected_hold_seconds")
    @classmethod
    def non_negative_seconds(cls, value: int | None) -> int | None:
        return None if value is None else max(0, int(value))

    @model_validator(mode="after")
    def bound_scores(self) -> "TimeSignal":
        for field in ("lockup_penalty_score", "urgency_score", "time_efficiency_score"):
            setattr(self, field, bounded(getattr(self, field)))
        return self


class FeeRewardSignal(BaseModel):
    market_id: str
    token_id: str | None = None
    side: TechnicalSide = TechnicalSide.UNKNOWN
    maker_cost_bps: float = 0.0
    taker_cost_bps: float = 0.0
    spread_cost_bps: float = 0.0
    slippage_cost_bps: float = 0.0
    reward_pool_usd: float = 0.0
    reward_score: float = 0.0
    net_edge_after_costs: float = 0.0
    fee_penalty_score: float = 0.0
    friction_score: float = 0.0
    source: str = "v2.8"
    raw_fee_reward: dict[str, Any] = Field(default_factory=dict)
    block_reason: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "FeeRewardSignal":
        for field in ("maker_cost_bps", "taker_cost_bps", "spread_cost_bps", "slippage_cost_bps", "reward_pool_usd"):
            setattr(self, field, non_negative(getattr(self, field)))
        for field in ("reward_score", "fee_penalty_score", "friction_score"):
            setattr(self, field, bounded(getattr(self, field)))
        return self


class TechnicalMarketTruth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_id: str
    market_signal: MarketTechnicalSignal
    orderbook_signal: OrderbookSignal
    liquidity_signal: LiquiditySignal
    time_signal: TimeSignal
    fee_reward_signal: FeeRewardSignal
    technical_score: float = 0.0
    technical_blocked: bool = False
    block_reasons: list[str] = Field(default_factory=list)
    data_completeness_score: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def normalize(self) -> "TechnicalMarketTruth":
        self.technical_score = bounded(self.technical_score)
        self.data_completeness_score = bounded(self.data_completeness_score)
        self.block_reasons = [reason for reason in dict.fromkeys(self.block_reasons) if reason]
        if self.block_reasons:
            self.technical_blocked = True
        return self

