from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.whale_neuron.redaction import redact_dict


class WhaleSourceType(StrEnum):
    POLYMARKET_PUBLIC = "POLYMARKET_PUBLIC"
    CLOB_PUBLIC = "CLOB_PUBLIC"
    MANUAL = "MANUAL"
    INTERNAL_PAPER = "INTERNAL_PAPER"
    CHAIN = "CHAIN"
    API = "API"
    CSV_IMPORT = "CSV_IMPORT"
    MOCK = "MOCK"


class WhaleSide(StrEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class WhaleActionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    ADD_LIQUIDITY = "ADD_LIQUIDITY"
    REMOVE_LIQUIDITY = "REMOVE_LIQUIDITY"
    TRANSFER = "TRANSFER"
    POSITION_OPEN = "POSITION_OPEN"
    POSITION_CLOSE = "POSITION_CLOSE"
    UNKNOWN = "UNKNOWN"


class WhaleEventClassification(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REVERSAL = "REVERSAL"
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"
    HEDGE = "HEDGE"
    MOMENTUM_CHASE = "MOMENTUM_CHASE"
    LATE_CHASE = "LATE_CHASE"
    MARKET_MOVER = "MARKET_MOVER"
    NOISE = "NOISE"
    UNKNOWN = "UNKNOWN"


class WhaleFollowDecisionValue(StrEnum):
    FOLLOW = "FOLLOW"
    WATCH = "WATCH"
    IGNORE = "IGNORE"
    PENALIZE = "PENALIZE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


def bounded(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(default if value is None else value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def stable_hash(value: Any) -> str:
    payload = json.dumps(redact_dict(value if isinstance(value, dict) else {"value": value}), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WhaleSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    name: str
    source_type: WhaleSourceType
    platform: str | None = None
    url: str | None = None
    enabled: bool = True
    reliability_score: float = 0.50
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_id", "name")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("field is required")
        return str(value).strip()

    @field_validator("reliability_score")
    @classmethod
    def score(cls, value: float) -> float:
        return bounded(value, 0.5)

    @model_validator(mode="after")
    def redact_metadata(self) -> "WhaleSource":
        self.metadata = redact_dict(self.metadata)
        return self


class WhaleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    whale_event_id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str
    whale_id: str | None = None
    wallet_address: str | None = None
    trader_label: str | None = None
    market_id: str | None = None
    asset_id: str | None = None
    side: WhaleSide = WhaleSide.UNKNOWN
    action_type: WhaleActionType = WhaleActionType.UNKNOWN
    size_usd: float | None = None
    size_shares: float | None = None
    price: float | None = None
    notional: float | None = None
    tx_hash: str | None = None
    order_id: str | None = None
    event_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_event: dict[str, Any] = Field(default_factory=dict)
    normalized_event: dict[str, Any] = Field(default_factory=dict)
    event_classification: WhaleEventClassification = WhaleEventClassification.UNKNOWN
    confidence: float = 0.0

    @model_validator(mode="after")
    def normalize_values(self) -> "WhaleEvent":
        self.raw_event = redact_dict(self.raw_event)
        self.normalized_event = redact_dict(self.normalized_event)
        if self.size_usd is not None:
            self.size_usd = max(0.0, float(self.size_usd))
        if self.size_shares is not None:
            self.size_shares = max(0.0, float(self.size_shares))
        if self.notional is None and self.size_usd is not None:
            self.notional = self.size_usd
        if self.notional is None and self.size_shares is not None and self.price is not None:
            self.notional = max(0.0, float(self.size_shares) * float(self.price))
        if self.whale_id is None:
            self.whale_id = self.wallet_address or self.trader_label or f"unknown_{stable_hash({'source': self.source_id, 'event': self.whale_event_id})[:12]}"
        self.confidence = bounded(self.confidence)
        return self


class WhaleRegistryRecord(BaseModel):
    whale_id: str
    wallet_address: str | None = None
    display_label: str | None = None
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_events: int = 0
    total_notional_usd: float = 0.0
    known_market_families: list[str] = Field(default_factory=list)
    status: str = "ACTIVE"


class WhaleProfile(BaseModel):
    whale_id: str
    hit_rate: float | None = None
    timing_quality: float = 0.0
    average_entry_quality: float | None = None
    average_exit_quality: float | None = None
    average_hold_time_seconds: float | None = None
    average_trade_size_usd: float | None = None
    win_consistency: float | None = None
    market_specialties: list[str] = Field(default_factory=list)
    follow_value: float = 0.0
    noise_score: float = 0.50
    momentum_chase_score: float = 0.0
    reversal_risk_score: float = 0.0
    copy_worthy_score: float = 0.0
    confidence: float = 0.0
    sample_size: int = 0

    @model_validator(mode="after")
    def bound_scores(self) -> "WhaleProfile":
        for field in ("timing_quality", "follow_value", "noise_score", "momentum_chase_score", "reversal_risk_score", "copy_worthy_score", "confidence"):
            setattr(self, field, bounded(getattr(self, field), 0.5 if field == "noise_score" else 0.0))
        if self.hit_rate is not None:
            self.hit_rate = bounded(self.hit_rate)
        return self


class WhaleCategory(BaseModel):
    whale_id: str
    category: str
    score: float = 0.0
    confidence: float = 0.0
    reason: str | None = None
    active: bool = True

    @field_validator("score", "confidence")
    @classmethod
    def bounded_scores(cls, value: float) -> float:
        return bounded(value)


class WhaleSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node: str = "whale"
    market_id: str
    whale_id: str
    side: WhaleSide = WhaleSide.UNKNOWN
    size_usd: float | None = None
    follow_value: float = 0.0
    noise_score: float = 0.0
    timing_quality: float = 0.0

    @field_validator("follow_value", "noise_score", "timing_quality")
    @classmethod
    def bounded_scores(cls, value: float) -> float:
        return bounded(value)

    @field_validator("size_usd")
    @classmethod
    def non_negative_size(cls, value: float | None) -> float | None:
        return None if value is None else max(0.0, float(value))


class WhaleMarketScore(BaseModel):
    whale_market_score_id: str = Field(default_factory=lambda: str(uuid4()))
    market_id: str
    whale_id: str
    whale_event_id: str | None = None
    side: WhaleSide = WhaleSide.UNKNOWN
    whale_presence_score: float = 0.0
    whale_conviction_score: float = 0.0
    smart_whale_alignment: float = 0.0
    whale_reversal_risk: float = 0.0
    follow_value: float = 0.0
    noise_penalty: float = 0.0
    confidence: float = 0.0
    signal: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def build_signal(self) -> "WhaleMarketScore":
        for field in ("whale_presence_score", "whale_conviction_score", "smart_whale_alignment", "whale_reversal_risk", "follow_value", "noise_penalty", "confidence"):
            setattr(self, field, bounded(getattr(self, field)))
        self.signal = WhaleSignal(
            market_id=self.market_id,
            whale_id=self.whale_id,
            side=self.side,
            size_usd=None,
            follow_value=self.follow_value,
            noise_score=self.noise_penalty,
            timing_quality=self.smart_whale_alignment,
        ).model_dump(mode="json")
        return self


class WhaleFollowDecision(BaseModel):
    whale_follow_decision_id: str = Field(default_factory=lambda: f"whale_follow_{uuid4().hex}")
    whale_id: str
    market_id: str | None = None
    whale_event_id: str | None = None
    decision: WhaleFollowDecisionValue = WhaleFollowDecisionValue.INSUFFICIENT_DATA
    follow_value: float = 0.0
    noise_score: float = 0.0
    confidence: float = 0.0
    reason: str | None = None

    @field_validator("follow_value", "noise_score", "confidence")
    @classmethod
    def bounded_scores(cls, value: float) -> float:
        return bounded(value)
