from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


EntityType = Literal[
    "person",
    "team",
    "asset",
    "token",
    "market",
    "source",
    "topic",
    "location",
    "organization",
    "event",
    "unknown",
]

LinkType = Literal["mentioned", "candidate_match", "manual", "rule_based", "alias_match", "exact_match", "inferred_by_brain"]
LinkStatus = Literal["suggested", "confirmed", "rejected", "expired", "unknown"]
ImpactScope = Literal["market", "position", "thesis", "source", "system", "unknown"]
ImpactDirection = Literal["favorable", "adverse", "neutral", "mixed", "unknown"]
ImpactStatus = Literal["suggested", "confirmed", "rejected", "expired", "needs_review", "unknown"]
CortexActionHint = Literal[
    "WATCH",
    "REVIEW",
    "NO_TRADE_REVIEW",
    "EXIT_REVIEW",
    "OPPORTUNITY_REVIEW",
    "RISK_REVIEW",
    "IGNORE",
    "MEMORY_ONLY",
    "UNKNOWN",
]

EXECUTABLE_CORTEX_HINTS = {
    "BUY",
    "SELL",
    "PLACE_ORDER",
    "CANCEL_ORDER",
    "EXECUTE",
    "LIVE_APPROVED",
    "ENTER_TRADE",
    "EXIT_TRADE",
    "OPEN_POSITION",
    "CLOSE_POSITION",
}


class EventEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: f"entity_{uuid4().hex}")
    entity_type: EntityType | str = "unknown"
    entity_name: str
    normalized_name: str | None = None
    source_signal_id: str | None = None
    source_event_id: str | None = None
    source_name: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("entity_type")
    @classmethod
    def normalize_entity_type(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        return normalized or "unknown"

    @field_validator("entity_name")
    @classmethod
    def require_entity_name(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("entity_name is required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class EntityMarketLink(BaseModel):
    entity_id: str
    market_id: str
    link_type: LinkType | str
    link_status: LinkStatus | str = "suggested"
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_signal_id: str | None = None
    evidence_event_id: str | None = None
    evidence_text: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("entity_id", "market_id", "link_type")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("entity_id, market_id, and link_type are required")
        return normalized

    @field_validator("link_status")
    @classmethod
    def normalize_link_status(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        return normalized or "unknown"

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SignalMarketLink(BaseModel):
    signal_id: str
    market_id: str
    link_type: LinkType | str
    link_status: LinkStatus | str = "suggested"
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("signal_id", "market_id", "link_type")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("signal_id, market_id, and link_type are required")
        return normalized

    @field_validator("link_status")
    @classmethod
    def normalize_link_status(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        return normalized or "unknown"

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SignalPositionLink(BaseModel):
    signal_id: str
    position_id: str
    market_id: str | None = None
    link_type: LinkType | str
    link_status: LinkStatus | str = "suggested"
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("signal_id", "position_id", "link_type")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("signal_id, position_id, and link_type are required")
        return normalized

    @field_validator("link_status")
    @classmethod
    def normalize_link_status(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        return normalized or "unknown"

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PositionThesisProfile(BaseModel):
    thesis_id: str = Field(default_factory=lambda: f"thesis_{uuid4().hex}")
    position_id: str
    market_id: str
    side: str | None = None
    entry_thesis: str
    profit_drivers: list[str] = Field(default_factory=list)
    invalidation_drivers: list[str] = Field(default_factory=list)
    watch_entities: list[str] = Field(default_factory=list)
    danger_signals: list[str] = Field(default_factory=list)
    take_profit_rules: list[str] = Field(default_factory=list)
    partial_exit_rules: list[str] = Field(default_factory=list)
    emergency_exit_rules: list[str] = Field(default_factory=list)
    status: str = "ACTIVE"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("position_id", "market_id", "entry_thesis", "status")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("position_id, market_id, entry_thesis, and status are required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ImpactLink(BaseModel):
    impact_link_id: str = Field(default_factory=lambda: f"impact_{uuid4().hex}")
    signal_id: str | None = None
    event_id: str | None = None
    entity_id: str | None = None
    market_id: str | None = None
    position_id: str | None = None
    thesis_id: str | None = None
    brain_output_id: str | None = None
    coordinator_decision_id: str | None = None
    impact_scope: ImpactScope | str
    impact_direction: ImpactDirection | str = "unknown"
    impact_status: ImpactStatus | str = "suggested"
    impact_strength: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    urgency: float | None = Field(default=None, ge=0, le=1)
    cortex_action_hint: CortexActionHint | str = "UNKNOWN"
    reasoning_summary: str | None = None
    created_by: str | None = None
    ttl_seconds: int | None = Field(default=None, ge=0)
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("impact_scope", "impact_direction", "impact_status")
    @classmethod
    def normalize_lower(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("impact scope, direction, and status are required")
        return normalized

    @field_validator("cortex_action_hint")
    @classmethod
    def validate_action_hint(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("cortex_action_hint is required")
        if normalized in EXECUTABLE_CORTEX_HINTS:
            raise ValueError("cortex_action_hint must not be executable")
        return normalized

    @model_validator(mode="after")
    def require_subject_and_target(self) -> "ImpactLink":
        if not (self.signal_id or self.event_id or self.entity_id):
            raise ValueError("impact link requires at least one subject")
        if not (
            self.market_id
            or self.position_id
            or self.thesis_id
            or self.impact_scope in {"system", "source"}
        ):
            raise ValueError("impact link requires at least one target")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def event_entity_from_row(row: dict[str, Any]) -> EventEntity:
    data = dict(row)
    data["metadata"] = data.pop("metadata_json", {}) or {}
    return EventEntity(**data)


def entity_market_link_from_row(row: dict[str, Any]) -> EntityMarketLink:
    return EntityMarketLink(**dict(row))


def signal_market_link_from_row(row: dict[str, Any]) -> SignalMarketLink:
    return SignalMarketLink(**dict(row))


def signal_position_link_from_row(row: dict[str, Any]) -> SignalPositionLink:
    return SignalPositionLink(**dict(row))


def position_thesis_profile_from_row(row: dict[str, Any]) -> PositionThesisProfile:
    data = dict(row)
    data["profit_drivers"] = data.pop("profit_drivers_json", []) or []
    data["invalidation_drivers"] = data.pop("invalidation_drivers_json", []) or []
    data["watch_entities"] = data.pop("watch_entities_json", []) or []
    data["danger_signals"] = data.pop("danger_signals_json", []) or []
    data["take_profit_rules"] = data.pop("take_profit_rules_json", []) or []
    data["partial_exit_rules"] = data.pop("partial_exit_rules_json", []) or []
    data["emergency_exit_rules"] = data.pop("emergency_exit_rules_json", []) or []
    return PositionThesisProfile(**data)


def impact_link_from_row(row: dict[str, Any]) -> ImpactLink:
    return ImpactLink(**dict(row))
