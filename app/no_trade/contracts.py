from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


NoTradeStatus = Literal["NO_TRADE", "BLOCKED", "REJECTED", "INSUFFICIENT_DATA", "WATCHLIST_ONLY"]
ReviewStatus = Literal["PENDING", "REVIEWED", "INSUFFICIENT_DATA", "EXPIRED"]
RegretBand = Literal["GOOD_NO_TRADE", "NEUTRAL", "MILD_REGRET", "HIGH_REGRET", "INSUFFICIENT_DATA"]


NORMALIZED_REASONS = {
    "low_edge",
    "low_liquidity",
    "wide_spread",
    "bad_rules",
    "high_wording_risk",
    "high_correlation",
    "no_capital",
    "bad_exit_quality",
    "already_priced_in",
    "high_slippage",
    "governor_block",
    "ai_uncertainty",
    "missing_exit_plan",
    "missing_risk_approval",
    "cooldown",
    "kill_switch",
    "stale_data",
    "insufficient_data",
    "unknown_reason",
}


def bounded(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(default if value is None else value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


class NoTradeReason(BaseModel):
    reason: str
    severity: str = "INFO"
    source_layer: str
    source_field: str | None = None
    penalty: float | None = None
    hard_block: bool = False
    explanation: str

    @model_validator(mode="after")
    def normalize(self) -> "NoTradeReason":
        self.reason = str(self.reason or "unknown_reason").lower()
        self.source_layer = str(self.source_layer or "system").lower()
        self.severity = str(self.severity or "INFO").upper()
        return self


class NoTradeDecision(BaseModel):
    no_trade_id: str = Field(default_factory=lambda: f"no_trade_{uuid4().hex}")
    market_id: str
    market_family: str | None = None
    side: str | None = None
    candidate_engine: str | None = None
    source_layer: str
    source_run_id: str | None = None
    source_record_id: str | None = None
    decision_status: NoTradeStatus = "NO_TRADE"
    primary_reason: str
    reasons: list[NoTradeReason] = Field(default_factory=list)
    risk_flags: list[dict[str, Any]] = Field(default_factory=list)
    opportunity_score: float | None = None
    strategy_route_status: str | None = None
    capital_allocation_status: str | None = None
    risk_gate_decision: str | None = None
    execution_block_reason: str | None = None
    exit_block_reason: str | None = None
    would_have_entry_price: float | None = None
    would_have_size_usd: float | None = None
    would_have_max_loss_usd: float | None = None
    decision_confidence: float = 0.0
    data_confidence: float = 0.0
    insufficient_data: bool = False
    insufficient_data_reasons: list[str] = Field(default_factory=list)
    explanation: str

    @model_validator(mode="after")
    def normalize(self) -> "NoTradeDecision":
        self.source_layer = str(self.source_layer or "").lower()
        self.primary_reason = str(self.primary_reason or "").lower()
        self.candidate_engine = None if self.candidate_engine is None else str(self.candidate_engine).upper()
        self.decision_confidence = bounded(self.decision_confidence)
        self.data_confidence = bounded(self.data_confidence)
        self.insufficient_data_reasons = list(dict.fromkeys(str(item) for item in self.insufficient_data_reasons))
        return self


class PostFactReview(BaseModel):
    review_id: str = Field(default_factory=lambda: f"no_trade_review_{uuid4().hex}")
    no_trade_id: str
    market_id: str
    review_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    review_horizon_seconds: int = 0
    observed_price_at_decision: float | None = None
    observed_price_after: float | None = None
    observed_max_favorable_move: float | None = None
    observed_max_adverse_move: float | None = None
    would_have_roi: float | None = None
    would_have_drawdown: float | None = None
    would_have_exit_possible: bool | None = None
    liquidity_after_score: float | None = None
    decision_correct: bool | None = None
    review_status: ReviewStatus = "PENDING"
    evidence: dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""


class NoTradeRegretScore(BaseModel):
    regret_id: str = Field(default_factory=lambda: f"no_trade_regret_{uuid4().hex}")
    no_trade_id: str
    market_id: str
    regret_score: float = 0.0
    regret_band: RegretBand = "INSUFFICIENT_DATA"
    missed_upside_score: float = 0.0
    avoided_loss_score: float = 0.0
    avoided_risk_score: float = 0.0
    liquidity_regret_score: float = 0.0
    confidence: float = 0.0
    learning_signal: str = "improve_data"
    update_memory: bool = False
    explanation: str = ""

    @model_validator(mode="after")
    def normalize(self) -> "NoTradeRegretScore":
        self.regret_score = bounded(self.regret_score)
        self.missed_upside_score = bounded(self.missed_upside_score)
        self.avoided_loss_score = bounded(self.avoided_loss_score)
        self.avoided_risk_score = bounded(self.avoided_risk_score)
        self.liquidity_regret_score = bounded(self.liquidity_regret_score)
        self.confidence = bounded(self.confidence)
        return self
