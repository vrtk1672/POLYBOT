from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ScoreBand = Literal["BLOCKED", "LOW", "WATCHLIST", "STRONG", "HIGH_CONVICTION"]
Severity = Literal["INFO", "WARNING", "BLOCKING"]


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


class OpportunityRiskFlag(BaseModel):
    risk_flag: str
    severity: Severity = "WARNING"
    source_type: str = "opportunity"
    source_id: str | None = None
    penalty: float = 0.0
    blocks_opportunity: bool = False
    explanation: str = ""

    @model_validator(mode="after")
    def normalize(self) -> "OpportunityRiskFlag":
        self.penalty = bounded(self.penalty)
        if self.severity == "BLOCKING":
            self.blocks_opportunity = True
        return self


class OpportunityInput(BaseModel):
    market_id: str
    market_family: str | None = None
    side: str = "UNKNOWN"
    context_output: dict[str, Any] = Field(default_factory=dict)
    capital_output: dict[str, Any] = Field(default_factory=dict)
    technical_truth: dict[str, Any] = Field(default_factory=dict)
    market_memory: dict[str, Any] = Field(default_factory=dict)
    news_signals: list[dict[str, Any]] = Field(default_factory=list)
    rules_signals: list[dict[str, Any]] = Field(default_factory=list)
    social_signals: list[dict[str, Any]] = Field(default_factory=list)
    whale_signals: list[dict[str, Any]] = Field(default_factory=list)
    fee_reward_signal: dict[str, Any] = Field(default_factory=dict)
    data_completeness_score: float = 0.0
    insufficient_data_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize(self) -> "OpportunityInput":
        self.side = str(self.side or "UNKNOWN").upper()
        if self.side not in {"YES", "NO", "UNKNOWN"}:
            raise ValueError("invalid opportunity side")
        self.data_completeness_score = bounded(self.data_completeness_score)
        self.insufficient_data_reasons = list(dict.fromkeys(self.insufficient_data_reasons))
        return self


class OpportunitySignalInput(BaseModel):
    source_type: str
    input_name: str
    source_id: str | None = None
    source_run_id: str | None = None
    input_value_numeric: float | None = None
    input_value_text: str | None = None
    input_json: dict[str, Any] | list[Any] | None = None
    weight: float = 0.0
    contribution: float = 0.0

    @model_validator(mode="after")
    def normalize(self) -> "OpportunitySignalInput":
        self.weight = float(self.weight or 0.0)
        self.contribution = float(self.contribution or 0.0)
        return self


class OpportunityScore(BaseModel):
    market_id: str
    side: str = "UNKNOWN"
    opportunity_score: float = 0.0
    score_band: ScoreBand = "LOW"
    edge: float = 0.0
    confidence: float = 0.0
    trigger_strength: float = 0.0
    repricing_potential: float = 0.0
    time_efficiency: float = 0.0
    liquidity_quality: float = 0.0
    exit_probability: float = 0.0
    capital_recycling_speed: float = 0.0
    convexity: float = 0.0
    balance_fit: float = 0.0
    fee_reward_advantage: float = 0.0
    risk_penalty: float = 0.0
    slippage_penalty: float = 0.0
    lockup_penalty: float = 0.0
    correlation_risk: float = 0.0
    trap_risk: float = 0.0
    wording_risk: float = 0.0
    adverse_selection_risk: float = 0.0
    already_priced_in_score: float = 0.0
    technical_blocked: bool = False
    capital_allowed: bool = False
    insufficient_data: bool = False
    insufficient_data_reasons: list[str] = Field(default_factory=list)
    risk_flags: list[OpportunityRiskFlag] = Field(default_factory=list)
    candidate_engines: list[str] = Field(default_factory=list)
    no_trade_reasons: list[str] = Field(default_factory=list)
    explanation: str = ""
    reproducibility_hash: str = ""

    @model_validator(mode="after")
    def normalize(self) -> "OpportunityScore":
        self.side = str(self.side or "UNKNOWN").upper()
        if self.side not in {"YES", "NO", "UNKNOWN"}:
            raise ValueError("invalid opportunity side")
        for field in (
            "opportunity_score",
            "edge",
            "confidence",
            "trigger_strength",
            "repricing_potential",
            "time_efficiency",
            "liquidity_quality",
            "exit_probability",
            "capital_recycling_speed",
            "convexity",
            "balance_fit",
            "fee_reward_advantage",
            "risk_penalty",
            "slippage_penalty",
            "lockup_penalty",
            "correlation_risk",
            "trap_risk",
            "wording_risk",
            "adverse_selection_risk",
            "already_priced_in_score",
        ):
            setattr(self, field, bounded(getattr(self, field)))
        self.insufficient_data_reasons = list(dict.fromkeys(self.insufficient_data_reasons))
        self.candidate_engines = list(dict.fromkeys(self.candidate_engines))
        self.no_trade_reasons = list(dict.fromkeys(self.no_trade_reasons))
        if any(flag.blocks_opportunity for flag in self.risk_flags):
            self.score_band = "BLOCKED"
            self.opportunity_score = 0.0
        return self


class OpportunityRunResult(BaseModel):
    run_id: str
    market_id: str
    side: str
    score: OpportunityScore
    signal_inputs: list[OpportunitySignalInput] = Field(default_factory=list)
    risk_flags: list[OpportunityRiskFlag] = Field(default_factory=list)
    persisted: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def reproducibility_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

