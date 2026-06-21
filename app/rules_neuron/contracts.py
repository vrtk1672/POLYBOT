from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.rules_neuron.redaction import redact_dict


class RulesRecommendation(StrEnum):
    TRADE_ALLOWED = "TRADE_ALLOWED"
    NO_TRADE = "NO_TRADE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PENALIZE_HEAVILY = "PENALIZE_HEAVILY"


class RulesStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    BLOCKED = "BLOCKED"
    WARNING = "WARNING"
    CLEAR = "CLEAR"
    BROKEN = "BROKEN"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class SettlementMethod(StrEnum):
    OBJECTIVE_SOURCE = "OBJECTIVE_SOURCE"
    PLATFORM_MANUAL = "PLATFORM_MANUAL"
    ORACLE = "ORACLE"
    SUBJECTIVE = "SUBJECTIVE"
    UNKNOWN = "UNKNOWN"


class ComplianceBlockType(StrEnum):
    MISSING_RULES = "MISSING_RULES"
    UNCLEAR_RESOLUTION = "UNCLEAR_RESOLUTION"
    UNVERIFIED_SOURCE = "UNVERIFIED_SOURCE"
    JURISDICTION_BLOCK = "JURISDICTION_BLOCK"
    AMBIGUOUS_DEADLINE = "AMBIGUOUS_DEADLINE"
    DISPUTE_RISK_HIGH = "DISPUTE_RISK_HIGH"
    PROHIBITED_CATEGORY = "PROHIBITED_CATEGORY"
    MANUAL_BLOCK = "MANUAL_BLOCK"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


def bounded(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        number = default
    return max(0.0, min(1.0, number))


def stable_hash(payload: dict[str, Any]) -> str:
    safe = redact_dict(payload)
    material = json.dumps(safe, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class RulesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_id: str
    rules_text: str | None = None
    resolution_source: str | None = None
    resolution_source_url: str | None = None
    deadline_at: datetime | None = None
    close_time: datetime | None = None
    question: str | None = None
    category: str | None = None
    market_family: str | None = None
    raw_market_json: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("market_id")
    @classmethod
    def market_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("market_id is required")
        return value.strip()

    @model_validator(mode="after")
    def redact(self) -> "RulesInput":
        self.raw_market_json = redact_dict(self.raw_market_json)
        self.metadata = redact_dict(self.metadata)
        return self


class ParsedRules(BaseModel):
    market_id: str
    rules_hash: str | None = None
    rules_text_present: bool = False
    resolution_source_present: bool = False
    deadline_present: bool = False
    settlement_method: SettlementMethod = SettlementMethod.UNKNOWN
    deadline_at: datetime | None = None
    ambiguous_terms: list[dict[str, Any]] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)
    dangerous_edge_cases: list[str] = Field(default_factory=list)


class ResolutionSourceStatus(BaseModel):
    market_id: str
    source_name: str | None = None
    source_url: str | None = None
    source_domain: str | None = None
    verification_status: RulesStatus = RulesStatus.UNKNOWN
    verification_reason: str | None = None
    reliability_score: float = 0.5

    @field_validator("reliability_score")
    @classmethod
    def bounded_reliability(cls, value: float) -> float:
        return bounded(value, 0.5)


class WordingRiskScore(BaseModel):
    wording_risk_id: str = Field(default_factory=lambda: f"wording_risk_{uuid4().hex}")
    market_id: str
    rules_analysis_id: str | None = None
    rules_hash: str | None = None
    ambiguity_score: float = 0.0
    deadline_risk: float = 0.0
    source_risk: float = 0.0
    scope_risk: float = 0.0
    settlement_risk: float = 0.0
    edge_case_risk: float = 0.0
    contradiction_risk: float = 0.0
    total_wording_risk: float = 0.0
    risk_terms: list[dict[str, Any]] = Field(default_factory=list)
    explanation: str | None = None

    @field_validator("ambiguity_score", "deadline_risk", "source_risk", "scope_risk", "settlement_risk", "edge_case_risk", "contradiction_risk", "total_wording_risk")
    @classmethod
    def bound_scores(cls, value: float) -> float:
        return bounded(value)


class DisputeRiskScore(BaseModel):
    market_id: str
    dispute_risk: float = 0.0
    factors: list[str] = Field(default_factory=list)
    explanation: str | None = None

    @field_validator("dispute_risk")
    @classmethod
    def bound_score(cls, value: float) -> float:
        return bounded(value)


class ComplianceBlock(BaseModel):
    compliance_block_id: str = Field(default_factory=lambda: f"compliance_block_{uuid4().hex}")
    market_id: str
    block_type: ComplianceBlockType
    severity: Severity
    reason: str
    source: str = "rules_neuron"
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComplianceDecision(BaseModel):
    market_id: str
    compliance_status: RulesStatus = RulesStatus.UNKNOWN
    blocks: list[ComplianceBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendation: RulesRecommendation = RulesRecommendation.REVIEW_REQUIRED
    cannot_trade_reason: str | None = None


class RulesAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    rules_analysis_id: str = Field(default_factory=lambda: f"rules_analysis_{uuid4().hex}")
    market_id: str
    rules_hash: str | None = None
    rules_text_present: bool = False
    resolution_source_present: bool = False
    deadline_present: bool = False
    settlement_method: SettlementMethod = SettlementMethod.UNKNOWN
    deadline_at: datetime | None = None
    ambiguous_terms: list[dict[str, Any]] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)
    dangerous_edge_cases: list[str] = Field(default_factory=list)
    wording_risk: float = 0.0
    dispute_risk: float = 0.0
    resolution_clarity: float = 0.0
    source_verification_status: RulesStatus = RulesStatus.UNKNOWN
    jurisdiction_status: RulesStatus = RulesStatus.UNKNOWN
    compliance_status: RulesStatus = RulesStatus.UNKNOWN
    recommendation: RulesRecommendation = RulesRecommendation.REVIEW_REQUIRED
    cannot_trade_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("wording_risk", "dispute_risk", "resolution_clarity")
    @classmethod
    def bound_scores(cls, value: float) -> float:
        return bounded(value)

    def signal(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "wording_risk": self.wording_risk,
            "dispute_risk": self.dispute_risk,
            "resolution_clarity": self.resolution_clarity,
            "dangerous_edge_cases": self.dangerous_edge_cases,
            "recommendation": self.recommendation.value if hasattr(self.recommendation, "value") else self.recommendation,
        }

