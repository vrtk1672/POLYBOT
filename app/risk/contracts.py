from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


RiskDecision = Literal["APPROVED", "BLOCKED", "REDUCED", "COOLDOWN", "INSUFFICIENT_DATA"]
GovernorStatus = Literal["OK", "WARNING", "COOLDOWN", "BLOCKED", "KILL", "INSUFFICIENT_DATA"]
Severity = Literal["INFO", "WARNING", "BLOCKING"]


def non_negative(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(default if value is None else value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, number)


def bounded(value: float | int | None, default: float = 0.0) -> float:
    return max(0.0, min(1.0, non_negative(value, default)))


class RiskLimit(BaseModel):
    scope: str = "GLOBAL"
    scope_key: str | None = None
    limit_type: str
    value: float | int | bool
    enabled: bool = True
    hard_limit: bool = True
    policy: dict[str, Any] = Field(default_factory=dict)


class RiskBreach(BaseModel):
    breach_id: str = Field(default_factory=lambda: f"risk_breach_{uuid4().hex}")
    limit_id: str | None = None
    breach_type: str
    severity: Severity = "WARNING"
    market_id: str | None = None
    market_family: str | None = None
    engine: str | None = None
    observed_value: float = 0.0
    limit_value: float = 0.0
    blocked: bool = False
    cooldown_created: bool = False
    explanation: str = ""

    @model_validator(mode="after")
    def normalize(self) -> "RiskBreach":
        self.observed_value = non_negative(self.observed_value)
        self.limit_value = non_negative(self.limit_value)
        if self.severity == "BLOCKING":
            self.blocked = True
        return self


class CooldownEvent(BaseModel):
    cooldown_id: str = Field(default_factory=lambda: f"risk_cooldown_{uuid4().hex}")
    scope: str = "GLOBAL"
    scope_key: str | None = None
    engine: str | None = None
    market_family: str | None = None
    market_id: str | None = None
    reason: str
    severity: Severity = "WARNING"
    active: bool = True
    expires_at: datetime | None = None
    source_breach_id: str | None = None


class RiskGovernorState(BaseModel):
    state_id: str = Field(default_factory=lambda: f"risk_state_{uuid4().hex}")
    runtime_mode: str | None = None
    governor_status: GovernorStatus = "OK"
    kill_switch_active: bool = False
    attack_mode_allowed: bool = False
    cooldown_active: bool = False
    daily_pnl_usd: float = 0.0
    weekly_pnl_usd: float = 0.0
    daily_loss_usd: float = 0.0
    weekly_loss_usd: float = 0.0
    open_positions_count: int = 0
    open_exposure_usd: float = 0.0
    max_daily_loss_usd: float = 50.0
    max_weekly_loss_usd: float = 150.0
    max_open_positions: int = 5
    max_total_exposure_usd: float = 500.0
    max_engine_loss: dict[str, float] = Field(default_factory=dict)
    max_market_family_exposure: dict[str, float] = Field(default_factory=dict)
    active_cooldowns: list[dict[str, Any]] = Field(default_factory=list)
    active_breaches: list[dict[str, Any]] = Field(default_factory=list)
    manual_overrides: list[dict[str, Any]] = Field(default_factory=list)
    data_confidence: float = 0.0
    insufficient_data: bool = False
    insufficient_data_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize(self) -> "RiskGovernorState":
        for field in ("daily_loss_usd", "weekly_loss_usd", "open_exposure_usd", "max_daily_loss_usd", "max_weekly_loss_usd", "max_total_exposure_usd"):
            setattr(self, field, non_negative(getattr(self, field)))
        self.open_positions_count = int(non_negative(self.open_positions_count))
        self.max_open_positions = int(non_negative(self.max_open_positions, 5))
        self.data_confidence = bounded(self.data_confidence)
        self.insufficient_data_reasons = list(dict.fromkeys(str(item) for item in self.insufficient_data_reasons))
        if self.kill_switch_active or str(self.runtime_mode or "").upper() == "KILL":
            self.governor_status = "KILL"
        elif self.insufficient_data:
            self.governor_status = "INSUFFICIENT_DATA"
        elif self.daily_loss_usd >= self.max_daily_loss_usd or self.weekly_loss_usd >= self.max_weekly_loss_usd:
            self.governor_status = "BLOCKED"
        elif self.cooldown_active:
            self.governor_status = "COOLDOWN"
        return self


class RiskGateInput(BaseModel):
    market_id: str
    market_family: str | None = None
    side: str = "UNKNOWN"
    engine: str = "NO_TRADE"
    strategy_route: dict[str, Any] = Field(default_factory=dict)
    capital_allocation: dict[str, Any] | None = None
    opportunity_score: dict[str, Any] = Field(default_factory=dict)
    technical_truth: dict[str, Any] = Field(default_factory=dict)
    rules_risk: dict[str, Any] = Field(default_factory=dict)
    market_memory: dict[str, Any] = Field(default_factory=dict)
    governor_state: RiskGovernorState | dict[str, Any] | None = None
    risk_limits: dict[str, Any] = Field(default_factory=dict)
    exit_plan_candidate: dict[str, Any] = Field(default_factory=dict)
    data_completeness_score: float = 0.0
    manual_override: dict[str, Any] | None = None

    @model_validator(mode="after")
    def normalize(self) -> "RiskGateInput":
        self.side = str(self.side or "UNKNOWN").upper()
        self.engine = str(self.engine or "NO_TRADE").upper()
        self.data_completeness_score = bounded(self.data_completeness_score)
        return self


class RiskGateDecision(BaseModel):
    run_id: str
    market_id: str
    market_family: str | None = None
    side: str = "UNKNOWN"
    engine: str = "NO_TRADE"
    decision: RiskDecision
    approved: bool = False
    blocked: bool = False
    risk_score: float = 0.0
    max_loss_usd: float = 0.0
    approved_max_loss_usd: float = 0.0
    approved_position_size_usd: float = 0.0
    liquidity_ok: bool = True
    slippage_ok: bool = True
    wording_risk_ok: bool = True
    correlation_ok: bool = True
    exposure_ok: bool = True
    engine_budget_ok: bool = True
    confidence_ok: bool = True
    exit_plan_ok: bool = True
    governor_ok: bool = True
    block_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    manual_override_used: bool = False
    override_id: str | None = None
    explanation: str = ""
    reproducibility_hash: str = ""

    @model_validator(mode="after")
    def normalize(self) -> "RiskGateDecision":
        self.risk_score = bounded(self.risk_score)
        self.max_loss_usd = non_negative(self.max_loss_usd)
        self.approved_max_loss_usd = non_negative(self.approved_max_loss_usd)
        self.approved_position_size_usd = non_negative(self.approved_position_size_usd)
        self.block_reasons = list(dict.fromkeys(str(item) for item in self.block_reasons))
        self.warnings = list(dict.fromkeys(str(item) for item in self.warnings))
        self.blocked = self.decision in {"BLOCKED", "COOLDOWN", "INSUFFICIENT_DATA"}
        self.approved = self.decision == "APPROVED"
        if self.blocked:
            self.approved_position_size_usd = 0.0
            self.approved_max_loss_usd = 0.0
        return self


def reproducibility_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

