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


class ContextBrainInput(BaseModel):
    market_id: str
    market_family: str | None = None
    news_signals: list[dict[str, Any]] = Field(default_factory=list)
    rules_signals: list[dict[str, Any]] = Field(default_factory=list)
    social_signals: list[dict[str, Any]] = Field(default_factory=list)
    whale_signals: list[dict[str, Any]] = Field(default_factory=list)
    technical_signals: list[dict[str, Any]] = Field(default_factory=list)
    memory_snapshot: dict[str, Any] = Field(default_factory=dict)
    ai_analysis: dict[str, Any] | None = None
    data_completeness_score: float = 0.0
    insufficient_data_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize(self) -> "ContextBrainInput":
        self.data_completeness_score = bounded(self.data_completeness_score)
        self.insufficient_data_reasons = list(dict.fromkeys(self.insufficient_data_reasons))
        return self


class ContextBrainOutput(BaseModel):
    market_id: str
    context_shift: bool = False
    direction: str = "UNKNOWN"
    strength: float = 0.0
    confidence: float = 0.0
    already_priced_in_score: float = 0.0
    ttl_seconds: int = 0
    urgency_score: float = 0.0
    risk_score: float = 0.0
    risks: list[str] = Field(default_factory=list)
    supporting_signals: list[dict[str, Any]] = Field(default_factory=list)
    contradicting_signals: list[dict[str, Any]] = Field(default_factory=list)
    insufficient_data: bool = False
    insufficient_data_reasons: list[str] = Field(default_factory=list)
    explanation: str = ""
    ai_context_summary: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "ContextBrainOutput":
        for name in ("strength", "confidence", "already_priced_in_score", "urgency_score", "risk_score"):
            setattr(self, name, bounded(getattr(self, name)))
        if self.direction not in {"YES", "NO", "UNKNOWN", "BOTH", "NONE"}:
            raise ValueError("invalid context direction")
        self.ttl_seconds = max(0, int(self.ttl_seconds or 0))
        self.risks = list(dict.fromkeys(self.risks))
        self.insufficient_data_reasons = list(dict.fromkeys(self.insufficient_data_reasons))
        return self


class CapitalBrainInput(BaseModel):
    market_id: str | None = None
    market_family: str | None = None
    candidate_engine: str | None = None
    balance: float | None = None
    available_capital: float | None = None
    locked_capital: float | None = None
    open_positions: list[dict[str, Any]] = Field(default_factory=list)
    engine_budgets: dict[str, float] = Field(default_factory=dict)
    risk_limits: dict[str, float] = Field(default_factory=dict)
    capital_recycling_speed: float = 0.0
    memory_snapshot: dict[str, Any] = Field(default_factory=dict)
    data_completeness_score: float = 0.0
    insufficient_data_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize(self) -> "CapitalBrainInput":
        self.capital_recycling_speed = bounded(self.capital_recycling_speed)
        self.data_completeness_score = bounded(self.data_completeness_score)
        self.insufficient_data_reasons = list(dict.fromkeys(self.insufficient_data_reasons))
        return self


class CapitalBrainOutput(BaseModel):
    market_id: str | None = None
    capital_allowed: bool = False
    block_reason: str | None = None
    max_position_size_usd: float | None = None
    risk_budget_usd: float | None = None
    capital_bucket: str | None = None
    cash_reserve_after_usd: float | None = None
    engine_budget_remaining_usd: float | None = None
    allocation_confidence: float = 0.0
    allocation_reason: str = ""
    insufficient_data: bool = False
    insufficient_data_reasons: list[str] = Field(default_factory=list)
    max_position_size_contracts: float | None = None
    available_capital_usd: float | None = None
    locked_capital_usd: float | None = None
    open_exposure_usd: float | None = None
    capital_recycling_score: float = 0.0
    constraints: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize(self) -> "CapitalBrainOutput":
        self.allocation_confidence = bounded(self.allocation_confidence)
        self.capital_recycling_score = bounded(self.capital_recycling_score)
        self.insufficient_data_reasons = list(dict.fromkeys(self.insufficient_data_reasons))
        self.constraints = list(dict.fromkeys(self.constraints))
        for name in ("max_position_size_usd", "risk_budget_usd", "cash_reserve_after_usd", "engine_budget_remaining_usd"):
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, max(0.0, float(value)))
        return self


class BrainCombinedSnapshot(BaseModel):
    market_id: str
    context_output: ContextBrainOutput
    capital_output: CapitalBrainOutput
    interesting: bool = False
    worth_money: bool = False
    ready_for_opportunity_cortex: bool = False
    reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def normalize(self) -> "BrainCombinedSnapshot":
        self.interesting = self.context_output.context_shift and self.context_output.confidence >= 0.25
        self.worth_money = self.interesting and self.capital_output.capital_allowed and self.capital_output.allocation_confidence >= 0.25
        self.ready_for_opportunity_cortex = self.interesting and not self.context_output.insufficient_data and not self.capital_output.insufficient_data
        self.reasons = list(dict.fromkeys(self.reasons))
        if self.interesting and not self.worth_money:
            self.reasons.append("interesting_not_worth_money")
        return self
