from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.events.correlation import get_current_correlation_id, new_correlation_id
from app.events.types import validate_event_type


SECRET_KEY_MARKERS = (
    "secret",
    "token",
    "password",
    "passphrase",
    "private",
    "credential",
    "api_key",
    "api_secret",
    "key",
)

PUBLIC_IDENTIFIER_KEYS = {
    "asset_id",
    "expected_token_id",
    "no_token_id",
    "token_id",
    "yes_token_id",
}


def _assert_json_serializable(value: dict[str, Any], field_name: str) -> dict[str, Any]:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be JSON serializable") from exc
    return value


def redact_event_data(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in PUBLIC_IDENTIFIER_KEYS:
                output[key] = redact_event_data(item)
            elif any(marker in key_text for marker in SECRET_KEY_MARKERS):
                output[key] = "<redacted>"
            else:
                output[key] = redact_event_data(item)
        return output
    if isinstance(value, list):
        return [redact_event_data(item) for item in value]
    return value


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    aggregate_type: str | None = None
    aggregate_id: str | None = None
    source_service: str
    correlation_id: str = Field(default_factory=lambda: get_current_correlation_id() or new_correlation_id())
    causation_id: str | None = None
    cycle_id: str | None = None
    mode: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = 1

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, value: str) -> str:
        return validate_event_type(value)

    @field_validator("source_service", "correlation_id")
    @classmethod
    def _required_non_empty(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("field is required")
        return str(value).strip()

    @field_validator("payload")
    @classmethod
    def _payload_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _assert_json_serializable(value, "payload")

    @field_validator("metadata")
    @classmethod
    def _metadata_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _assert_json_serializable(value, "metadata")

    def redacted_payload(self) -> dict[str, Any]:
        return redact_event_data(self.payload)

    def redacted_metadata(self) -> dict[str, Any]:
        return redact_event_data(self.metadata)

    def safe_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["payload"] = self.redacted_payload()
        data["metadata"] = self.redacted_metadata()
        return data

    @classmethod
    def from_record(cls, row: dict[str, Any]) -> "EventEnvelope":
        return cls(
            event_id=row["event_id"],
            event_type=row["event_type"],
            aggregate_type=row.get("aggregate_type"),
            aggregate_id=row.get("aggregate_id"),
            source_service=row["source_service"],
            correlation_id=row["correlation_id"],
            causation_id=row.get("causation_id"),
            cycle_id=row.get("cycle_id"),
            mode=row.get("mode"),
            occurred_at=row["occurred_at"],
            payload=row.get("payload_json") or {},
            metadata=row.get("metadata_json") or {},
            schema_version=row.get("schema_version") or 1,
        )
