from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


def bounded(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(default if value is None else value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def avg(values: list[float | int | None]) -> float | None:
    clean = [float(v) for v in values if v is not None]
    return None if not clean else sum(clean) / len(clean)


class MemoryBase(BaseModel):
    summary: dict[str, Any] = Field(default_factory=dict)


class MarketMemory(MemoryBase):
    market_id: str
    market_family: str | None = None
    best_engine: str = "UNKNOWN"
    avg_spread_bps: float | None = None
    avg_depth_2c: float | None = None
    avg_fill_rate: float | None = None
    avg_slippage_bps: float | None = None
    avg_hold_seconds: float | None = None
    false_signal_rate: float = 0.0
    wording_risk_avg: float | None = None
    memory_confidence: float = 0.0
    memory_status: str = "insufficient_data"
    observations_count: int = 0
    technical_block_rate: float = 0.0
    liquidity_failure_rate: float = 0.0
    stale_data_rate: float = 0.0
    avg_price: float | None = None
    avg_depth_1c: float | None = None
    avg_depth_5c: float | None = None
    avg_exit_quality: float | None = None
    avg_time_efficiency: float | None = None
    dispute_risk_avg: float | None = None

    @model_validator(mode="after")
    def normalize(self) -> "MarketMemory":
        for name in ("false_signal_rate", "memory_confidence", "technical_block_rate", "liquidity_failure_rate", "stale_data_rate"):
            setattr(self, name, bounded(getattr(self, name)))
        if self.observations_count > 0 and self.memory_confidence >= 0.15:
            self.memory_status = "active"
        return self


class MarketFamilyMemory(MemoryBase):
    market_family: str
    best_engine: str = "UNKNOWN"
    strike_win_rate: float | None = None
    convex_hit_rate: float | None = None
    maker_adverse_selection_rate: float | None = None
    avg_spread_bps: float | None = None
    avg_depth_2c: float | None = None
    avg_slippage_bps: float | None = None
    technical_block_rate: float = 0.0
    memory_confidence: float = 0.0
    observations_count: int = 0
    markets_count: int = 0

    @model_validator(mode="after")
    def normalize(self) -> "MarketFamilyMemory":
        self.technical_block_rate = bounded(self.technical_block_rate)
        self.memory_confidence = bounded(self.memory_confidence)
        return self


class EnginePerformanceMemory(MemoryBase):
    engine: str
    market_family: str = "UNKNOWN"
    win_rate: float = 0.0
    avg_roi: float | None = None
    avg_roi_per_hour: float | None = None
    avg_hold_seconds: float | None = None
    adverse_selection_rate: float = 0.0
    engine_score: float = 0.0
    confidence: float = 0.0
    observations_count: int = 0
    wins_count: int = 0
    losses_count: int = 0
    neutral_count: int = 0

    @model_validator(mode="after")
    def normalize(self) -> "EnginePerformanceMemory":
        for name in ("win_rate", "adverse_selection_rate", "engine_score", "confidence"):
            setattr(self, name, bounded(getattr(self, name)))
        return self


class SourceReliabilityMemory(MemoryBase):
    source_type: str
    source_name: str
    reliability_score: float = 0.5
    usefulness_score: float = 0.0
    true_positive_count: int = 0
    false_positive_count: int = 0
    avg_latency_seconds: float | None = None
    confidence: float = 0.0
    observations_count: int = 0
    source_id: str | None = None
    market_family: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "SourceReliabilityMemory":
        for name in ("reliability_score", "usefulness_score", "confidence"):
            setattr(self, name, bounded(getattr(self, name), 0.5 if name == "reliability_score" else 0.0))
        return self


class WhaleMemory(MemoryBase):
    whale_id: str
    market_family: str | None = None
    hit_rate: float | None = None
    follow_value_avg: float = 0.0
    noise_score_avg: float = 0.5
    reversal_rate: float = 0.0
    whale_score: float = 0.0
    confidence: float = 0.0
    observations_count: int = 0
    avg_timing_quality: float | None = None
    avg_size_usd: float | None = None

    @model_validator(mode="after")
    def normalize(self) -> "WhaleMemory":
        for name in ("follow_value_avg", "noise_score_avg", "reversal_rate", "whale_score", "confidence"):
            setattr(self, name, bounded(getattr(self, name), 0.5 if name == "noise_score_avg" else 0.0))
        if self.hit_rate is not None:
            self.hit_rate = bounded(self.hit_rate)
        return self


class SlippageMemory(MemoryBase):
    market_family: str | None = None
    avg_expected_slippage_bps: float | None = None
    avg_realized_slippage_bps: float | None = None
    slippage_error_bps: float | None = None
    failed_fill_rate: float = 0.0
    slippage_risk_score: float = 0.0
    confidence: float = 0.0
    observations_count: int = 0
    market_id: str | None = None
    token_id: str | None = None
    side: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "SlippageMemory":
        for name in ("failed_fill_rate", "slippage_risk_score", "confidence"):
            setattr(self, name, bounded(getattr(self, name)))
        return self


class RulesRiskMemory(MemoryBase):
    market_family: str | None = None
    avg_wording_risk: float | None = None
    avg_dispute_risk: float | None = None
    avg_resolution_clarity: float | None = None
    settlement_delay_avg_seconds: float | None = None
    rules_risk_score: float = 0.0
    confidence: float = 0.0
    observations_count: int = 0
    market_id: str | None = None
    ambiguous_terms_count: int = 0
    edge_case_count: int = 0
    rules_block_rate: float = 0.0

    @model_validator(mode="after")
    def normalize(self) -> "RulesRiskMemory":
        self.rules_risk_score = bounded(self.rules_risk_score)
        self.rules_block_rate = bounded(self.rules_block_rate)
        self.confidence = bounded(self.confidence)
        return self


class NoTradeMemory(MemoryBase):
    market_family: str | None = None
    candidate_engine: str | None = None
    reason: str
    regret_rate: float = 0.0
    avg_would_have_roi: float | None = None
    no_trade_quality_score: float = 0.0
    confidence: float = 0.0
    observations_count: int = 0
    market_id: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "NoTradeMemory":
        self.regret_rate = bounded(self.regret_rate)
        self.no_trade_quality_score = bounded(self.no_trade_quality_score)
        self.confidence = bounded(self.confidence)
        return self


class MarketMemorySnapshot(BaseModel):
    market_id: str
    market_family: str | None = None
    market_memory: MarketMemory | None = None
    market_family_memory: MarketFamilyMemory | None = None
    engine_memory: list[EnginePerformanceMemory] = Field(default_factory=list)
    source_memory: list[SourceReliabilityMemory] = Field(default_factory=list)
    whale_memory: list[WhaleMemory] = Field(default_factory=list)
    slippage_memory: list[SlippageMemory] = Field(default_factory=list)
    rules_risk_memory: list[RulesRiskMemory] = Field(default_factory=list)
    no_trade_memory: list[NoTradeMemory] = Field(default_factory=list)
    confidence: float = 0.0
    insufficient_data: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def normalize(self) -> "MarketMemorySnapshot":
        self.confidence = bounded(self.confidence)
        self.insufficient_data = list(dict.fromkeys(self.insufficient_data))
        return self
