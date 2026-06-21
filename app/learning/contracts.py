from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class TradeReview(BaseModel):
    review_id: str = Field(default_factory=lambda: _id("trv"))
    trade_id: str | None = None
    order_id: str | None = None
    exit_plan_id: str | None = None
    exit_intent_id: str | None = None
    market_id: str
    market_family: str | None = None
    side: str | None = None
    engine: str | None = None
    strategy_route_id: str | None = None
    opportunity_run_id: str | None = None
    capital_allocation_id: str | None = None
    risk_gate_run_id: str | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    hold_seconds: int | None = None
    realized_pnl_usd: float | None = None
    realized_roi: float | None = None
    roi_per_hour: float | None = None
    max_favorable_excursion: float | None = None
    max_adverse_excursion: float | None = None
    entry_quality_score: float | None = None
    exit_quality_score: float | None = None
    slippage_accuracy_score: float | None = None
    signal_accuracy_score: float | None = None
    engine_result: str = "UNKNOWN"
    review_status: str = "PENDING"
    insufficient_data: bool = False
    insufficient_data_reasons: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    explanation: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SignalPerformance(BaseModel):
    signal_perf_id: str = Field(default_factory=lambda: _id("sig"))
    source_type: str
    source_id: str | None = None
    signal_type: str
    market_id: str | None = None
    market_family: str | None = None
    direction: str | None = None
    predicted_strength: float | None = None
    observed_move: float | None = None
    observed_direction: str | None = None
    accuracy_score: float
    usefulness_score: float
    false_positive: bool | None = None
    false_negative: bool | None = None
    latency_seconds: int | None = None
    confidence: float
    evidence: dict[str, Any] = Field(default_factory=dict)


class EngineLearning(BaseModel):
    engine_learning_id: str = Field(default_factory=lambda: _id("eng"))
    engine: str
    market_family: str | None = None
    market_id: str | None = None
    review_id: str | None = None
    no_trade_id: str | None = None
    observation_type: str
    result: str
    prior_engine_score: float | None = None
    new_engine_score: float | None = None
    win_rate_delta: float | None = None
    roi_delta: float | None = None
    slippage_penalty_delta: float | None = None
    adverse_selection_delta: float | None = None
    confidence: float
    learning_signal: str
    explanation: str


class SourceLearning(BaseModel):
    source_learning_id: str = Field(default_factory=lambda: _id("src"))
    source_type: str
    source_name: str | None = None
    source_id: str | None = None
    market_family: str | None = None
    observation_type: str
    result: str
    prior_reliability: float | None = None
    new_reliability: float | None = None
    usefulness_delta: float | None = None
    latency_delta: float | None = None
    confidence: float
    learning_signal: str
    explanation: str


class WhaleLearning(BaseModel):
    whale_learning_id: str = Field(default_factory=lambda: _id("whale"))
    whale_id: str
    market_family: str | None = None
    market_id: str | None = None
    observation_type: str
    result: str
    prior_follow_value: float | None = None
    new_follow_value: float | None = None
    prior_noise_score: float | None = None
    new_noise_score: float | None = None
    hit_rate_delta: float | None = None
    timing_quality_delta: float | None = None
    confidence: float
    learning_signal: str
    explanation: str


class AILearning(BaseModel):
    ai_learning_id: str = Field(default_factory=lambda: _id("ai"))
    ai_request_id: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    market_id: str | None = None
    market_family: str | None = None
    task_type: str
    predicted_output: dict[str, Any] | None = None
    observed_outcome: dict[str, Any] | None = None
    usefulness_score: float
    accuracy_score: float
    cost_usd: float | None = None
    cost_efficiency_score: float | None = None
    prior_model_score: float | None = None
    new_model_score: float | None = None
    confidence: float
    learning_signal: str
    explanation: str


class NoTradeLearning(BaseModel):
    no_trade_learning_id: str = Field(default_factory=lambda: _id("ntl"))
    no_trade_id: str
    market_id: str
    market_family: str | None = None
    candidate_engine: str | None = None
    regret_band: str
    regret_score: float | None = None
    learning_signal: str
    suggested_filter_change: str | None = None
    confidence: float
    explanation: str


class ModelAdjustment(BaseModel):
    adjustment_id: str = Field(default_factory=lambda: _id("adj"))
    adjustment_type: str
    target_module: str
    target_key: str | None = None
    current_value: str | None = None
    recommended_value: str | None = None
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    confidence: float
    status: str = "RECOMMENDED"


class MemoryUpdateDecision(BaseModel):
    allowed: bool
    update_memory: bool
    confidence: float
    reason: str
