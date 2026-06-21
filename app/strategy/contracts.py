from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


EngineName = Literal["SAFE", "STRIKE", "CONVEX", "MAKER", "HUNT", "MOONSHOT_BASKET", "REINVEST", "NO_TRADE"]
RouteStatus = Literal["ROUTED", "NO_TRADE", "BLOCKED", "WATCHLIST", "COOLDOWN", "INSUFFICIENT_DATA"]
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


class StrategyRouteInput(BaseModel):
    market_id: str
    market_family: str | None = None
    side: str = "UNKNOWN"
    opportunity_run_id: str | None = None
    opportunity_score_id: int | None = None
    opportunity_score: float = 0.0
    opportunity_score_band: str = "LOW"
    opportunity_components: dict[str, Any] = Field(default_factory=dict)
    opportunity_risk_flags: list[dict[str, Any]] = Field(default_factory=list)
    opportunity_no_trade_reasons: list[str] = Field(default_factory=list)
    candidate_engines_from_opportunity: list[str] = Field(default_factory=list)
    context_output: dict[str, Any] = Field(default_factory=dict)
    capital_output: dict[str, Any] = Field(default_factory=dict)
    technical_truth: dict[str, Any] = Field(default_factory=dict)
    market_memory: dict[str, Any] = Field(default_factory=dict)
    runtime_state: dict[str, Any] = Field(default_factory=dict)
    data_completeness_score: float = 0.0
    insufficient_data_reasons: list[str] = Field(default_factory=list)
    hunt_approval: bool = False

    @model_validator(mode="after")
    def normalize(self) -> "StrategyRouteInput":
        self.side = str(self.side or "UNKNOWN").upper()
        if self.side not in {"YES", "NO", "UNKNOWN"}:
            raise ValueError("invalid strategy side")
        self.opportunity_score = bounded(self.opportunity_score)
        self.data_completeness_score = bounded(self.data_completeness_score)
        self.opportunity_score_band = str(self.opportunity_score_band or "LOW").upper()
        self.candidate_engines_from_opportunity = [str(item).upper() for item in self.candidate_engines_from_opportunity]
        self.opportunity_no_trade_reasons = list(dict.fromkeys(str(item) for item in self.opportunity_no_trade_reasons))
        self.insufficient_data_reasons = list(dict.fromkeys(str(item) for item in self.insufficient_data_reasons))
        return self


class EngineContract(BaseModel):
    engine: EngineName
    market_id: str
    side: str = "UNKNOWN"
    entry_conditions: dict[str, Any] = Field(default_factory=dict)
    exit_conditions: dict[str, Any] = Field(default_factory=dict)
    risk_limits: dict[str, Any] = Field(default_factory=dict)
    position_sizing_rules: dict[str, Any] = Field(default_factory=dict)
    allowed_market_families: list[str] = Field(default_factory=list)
    forbidden_conditions: list[str] = Field(default_factory=list)
    cooldown_triggers: list[str] = Field(default_factory=list)
    expected_hold_minutes: int = 0
    entry_price_max: float | None = None
    target_exit: float | None = None
    partial_take_profit: float | None = None
    stop_loss: float | None = None
    max_position_size_usd: float = 0.0
    max_position_size_contracts: float | None = None
    max_loss_usd: float = 0.0
    entry_mode: str = "NONE"
    exit_mode: str = "NONE"
    execution_mode: str = "CONTRACT_ONLY"
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self) -> "EngineContract":
        self.side = str(self.side or "UNKNOWN").upper()
        if self.side not in {"YES", "NO", "UNKNOWN"}:
            raise ValueError("invalid contract side")
        self.max_position_size_usd = non_negative(self.max_position_size_usd)
        self.max_loss_usd = non_negative(self.max_loss_usd)
        self.expected_hold_minutes = int(non_negative(self.expected_hold_minutes))
        self.execution_mode = "CONTRACT_ONLY"
        return self


class EngineDecision(BaseModel):
    engine: EngineName
    eligible: bool = False
    selected: bool = False
    engine_score: float = 0.0
    confidence: float = 0.0
    contract: EngineContract | None = None
    rejection_reason: str | None = None
    severity: Severity = "INFO"

    @model_validator(mode="after")
    def normalize(self) -> "EngineDecision":
        self.engine_score = bounded(self.engine_score)
        self.confidence = bounded(self.confidence)
        if not self.eligible and not self.rejection_reason:
            self.rejection_reason = "engine_not_eligible"
        if self.engine == "NO_TRADE":
            self.eligible = True
        return self


class EngineRejection(BaseModel):
    engine: EngineName
    rejection_reason: str
    severity: Severity = "WARNING"
    source_type: str = "strategy"
    source_id: str | None = None
    hard_block: bool = False
    explanation: str = ""

    @model_validator(mode="after")
    def normalize(self) -> "EngineRejection":
        if self.severity == "BLOCKING":
            self.hard_block = True
        return self


class StrategyRoute(BaseModel):
    market_id: str
    side: str = "UNKNOWN"
    selected_engine: EngineName = "NO_TRADE"
    route_status: RouteStatus = "NO_TRADE"
    opportunity_score: float = 0.0
    score_band: str = "LOW"
    route_confidence: float = 0.0
    contract: EngineContract | None = None
    engine_decisions: list[EngineDecision] = Field(default_factory=list)
    engine_rejections: list[EngineRejection] = Field(default_factory=list)
    no_trade_reasons: list[str] = Field(default_factory=list)
    risk_flags: list[dict[str, Any]] = Field(default_factory=list)
    cooldown_required: bool = False
    insufficient_data: bool = False
    insufficient_data_reasons: list[str] = Field(default_factory=list)
    reproducibility_hash: str = ""
    route_reason: str = ""

    @model_validator(mode="after")
    def normalize(self) -> "StrategyRoute":
        self.side = str(self.side or "UNKNOWN").upper()
        self.opportunity_score = bounded(self.opportunity_score)
        self.route_confidence = bounded(self.route_confidence)
        self.no_trade_reasons = list(dict.fromkeys(str(item) for item in self.no_trade_reasons))
        self.insufficient_data_reasons = list(dict.fromkeys(str(item) for item in self.insufficient_data_reasons))
        if self.selected_engine == "NO_TRADE":
            if self.route_status == "ROUTED":
                self.route_status = "NO_TRADE"
        elif self.contract is None:
            raise ValueError("non-NO_TRADE route requires a full engine contract")
        return self


class StrategyRunResult(BaseModel):
    run_id: str
    market_id: str
    side: str
    route: StrategyRoute
    persisted: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def reproducibility_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

