from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


SignalStatus = Literal["ACTIVE", "PARTIAL", "DEGRADED", "STALE", "DISABLED", "MISSING", "ERROR"]
RawDirection = Literal[
    "positive",
    "negative",
    "neutral",
    "mixed",
    "unknown",
    "yes_up",
    "yes_down",
    "no_up",
    "no_down",
    "entity_positive",
    "entity_negative",
]

KNOWN_NEURONS = {
    "market",
    "orderbook",
    "liquidity",
    "rules",
    "resolution",
    "news",
    "social",
    "whale",
    "time",
    "fees",
    "ai",
    "risk",
    "capital",
    "position",
    "exit",
    "unknown",
}

FORBIDDEN_EVIDENCE_KEYS = {
    "buy",
    "sell",
    "enter_trade",
    "exit_trade",
    "trade_decision",
    "approved",
    "rejected",
    "order_id",
}


class NeuronSignal(BaseModel):
    signal_id: str = Field(default_factory=lambda: f"signal_{uuid4().hex}")
    neuron: str
    event_type: str
    source_name: str | None = None
    market_id: str | None = None
    correlation_id: str | None = None
    raw_direction: RawDirection | None = None
    strength: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_reliability: float | None = Field(default=None, ge=0, le=1)
    freshness_seconds: int | None = Field(default=None, ge=0)
    status: SignalStatus
    evidence: dict[str, Any] = Field(default_factory=dict)
    raw_payload_ref: str | None = None
    entity_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    processed_by_brain: bool = False
    consumed_at: datetime | None = None
    ttl_seconds: int | None = Field(default=None, ge=0)
    expires_at: datetime | None = None
    stale_after_seconds: int | None = Field(default=None, ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("neuron")
    @classmethod
    def normalize_neuron(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("neuron is required")
        return normalized if normalized in KNOWN_NEURONS else normalized

    @field_validator("event_type")
    @classmethod
    def require_event_type(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("event_type is required")
        return normalized

    @model_validator(mode="after")
    def reject_decision_payload(self) -> "NeuronSignal":
        forbidden = FORBIDDEN_EVIDENCE_KEYS.intersection(set(self.evidence))
        if forbidden:
            raise ValueError(f"signal evidence contains decision/order keys: {sorted(forbidden)}")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class NeuronSignalEntity(BaseModel):
    signal_id: str
    entity_type: str
    entity_name: str
    entity_id: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class NeuronSignalEvidence(BaseModel):
    signal_id: str
    evidence_type: str
    evidence_text: str | None = None
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    source_url: str | None = None


def signal_from_row(row: dict[str, Any]) -> NeuronSignal:
    data = dict(row)
    data["evidence"] = data.pop("evidence_json", {}) or {}
    return NeuronSignal(**data)
