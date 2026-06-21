from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.events.envelope import redact_event_data
from app.neural_bus.types import validate_neural_event_type
from app.utils.json_safety import json_dumps, json_safe


class NeuralEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"neural_event_{uuid4().hex}")
    event_type: str
    correlation_id: str | None = None
    market_id: str | None = None
    candidate_id: str | None = None
    position_id: str | None = None
    source_component: str
    source_type: str
    priority: int = Field(default=5, ge=0, le=10)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    consumed_count: int = 0
    status: str = "PUBLISHED"
    source_table: str | None = None
    source_record_id: str | None = None
    schema_version: int = 1
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _event_type(cls, value: str) -> str:
        return validate_neural_event_type(value)

    @field_validator("source_component", "source_type")
    @classmethod
    def _required(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("field is required")
        return value

    @field_validator("payload_json", "metadata_json")
    @classmethod
    def _json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        safe = json_safe(value)
        json_dumps(safe)
        return safe

    def safe_payload(self) -> dict[str, Any]:
        return redact_event_data(json_safe(self.payload_json))

    def safe_metadata(self) -> dict[str, Any]:
        return redact_event_data(json_safe(self.metadata_json))

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "NeuralEvent":
        return cls(
            event_id=row["event_id"],
            event_type=row["event_type"],
            correlation_id=row.get("correlation_id"),
            market_id=row.get("market_id"),
            candidate_id=row.get("candidate_id"),
            position_id=row.get("position_id"),
            source_component=row["source_component"],
            source_type=row["source_type"],
            priority=int(row.get("priority") or 5),
            payload_json=dict(row.get("payload_json") or {}),
            created_at=row.get("created_at"),
            consumed_count=int(row.get("consumed_count") or 0),
            status=row.get("status") or "PUBLISHED",
            source_table=row.get("source_table"),
            source_record_id=row.get("source_record_id"),
            schema_version=int(row.get("schema_version") or 1),
            metadata_json=dict(row.get("metadata_json") or {}),
        )

