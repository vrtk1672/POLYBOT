from __future__ import annotations

import json
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.events.correlation import get_current_correlation_id, new_correlation_id
from app.ai_brain.redaction import redact_dict, redact_text


class AITaskType(StrEnum):
    MARKET_CLASSIFICATION = "MARKET_CLASSIFICATION"
    RULES_SUMMARY = "RULES_SUMMARY"
    MARKET_LINKING = "MARKET_LINKING"
    NEWS_DEDUP = "NEWS_DEDUP"
    CONTEXT_SUMMARY = "CONTEXT_SUMMARY"
    CASE_FILE_BUILD = "CASE_FILE_BUILD"
    WORDING_RISK_PRECHECK = "WORDING_RISK_PRECHECK"
    CONTRADICTION_CHECK = "CONTRADICTION_CHECK"
    TRAP_PRECHECK = "TRAP_PRECHECK"
    POST_TRADE_REVIEW_PREP = "POST_TRADE_REVIEW_PREP"


class AIModelTier(StrEnum):
    LOCAL_FAST = "LOCAL_FAST"
    LOCAL_PRIMARY = "LOCAL_PRIMARY"
    LOCAL_REASONING = "LOCAL_REASONING"
    CLOUD_ESCALATION = "CLOUD_ESCALATION"


def normalize_task_type(value: AITaskType | str) -> AITaskType:
    if isinstance(value, AITaskType):
        return value
    try:
        return AITaskType(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"unknown ai task_type: {value}") from exc


def _assert_json_serializable(value: dict[str, Any], field_name: str) -> dict[str, Any]:
    try:
        json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be JSON serializable") from exc
    return value


class AIModelRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: AITaskType
    selected_tier: AIModelTier
    selected_model: str
    provider: str
    reason: str
    cloud_allowed: bool = False
    cache_required: bool = True
    budget_required: bool = True


class AIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: AITaskType
    market_id: str | None = None
    event_id: str | None = None
    correlation_id: str = Field(default_factory=lambda: get_current_correlation_id() or new_correlation_id())
    input_payload: dict[str, Any] = Field(default_factory=dict)
    prompt_version_id: str | None = None
    max_cost: float | None = None
    require_json_output: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input_payload", "metadata")
    @classmethod
    def _json_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _assert_json_serializable(value, "payload")

    @field_validator("correlation_id")
    @classmethod
    def _correlation_required(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("correlation_id is required")
        return str(value).strip()

    def safe_payload(self) -> dict[str, Any]:
        return redact_dict(self.input_payload)


class AIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_request_id: str = Field(default_factory=lambda: f"ai_req_{uuid4().hex}")
    task_type: AITaskType
    model_name: str
    structured_output: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    risk_flags: list[str] = Field(default_factory=list)
    recommended_action: str | None = None
    raw_output_redacted: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("structured_output", "metadata")
    @classmethod
    def _json_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _assert_json_serializable(value, "response")

    @field_validator("raw_output_redacted")
    @classmethod
    def _redact_raw(cls, value: str | None) -> str | None:
        return redact_text(value)


class AIDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_type: str
    task_type: AITaskType
    market_id: str | None = None
    confidence: float | None = None
    output_json: dict[str, Any] = Field(default_factory=dict)
    risk_flags: list[str] = Field(default_factory=list)
    cannot_trade_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("output_json", "metadata")
    @classmethod
    def _json_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _assert_json_serializable(value, "decision")

    @model_validator(mode="after")
    def _no_execution_fields(self) -> "AIDecision":
        forbidden = {"order_id", "order_intent_id", "trade_id", "position_id", "risk_approved"}
        if forbidden & set(self.output_json):
            raise ValueError("AI decisions cannot contain trade execution fields")
        return self


class AICaseFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_id: str | None = None
    question: str | None = None
    category: str | None = None
    market_family: str | None = None
    prices: dict[str, Any] = Field(default_factory=dict)
    bid_ask: dict[str, Any] = Field(default_factory=dict)
    spread: float | None = None
    liquidity: dict[str, Any] = Field(default_factory=dict)
    time_to_close: int | None = None
    rules_summary_or_text: str | None = None
    resolution_source: str | None = None
    data_completeness_score: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    stale_fields: list[str] = Field(default_factory=list)
    orderbook_missing: bool = True
    rules_missing: bool = True
    latest_events_summary: list[dict[str, Any]] = Field(default_factory=list)
    allowed_for_ai: bool = False
    blocked_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prices", "bid_ask", "liquidity", "metadata")
    @classmethod
    def _json_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _assert_json_serializable(redact_dict(value), "case_file")

    def compact_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["metadata"] = redact_dict(data.get("metadata") or {})
        return data
