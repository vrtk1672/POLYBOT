from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


GeneratedFrom = Literal["source_status", "rules_resolution", "event_log", "manual", "dashboard", "future_connector", "unknown"]


class SignalLineage(BaseModel):
    signal_id: str
    neuron_name: str
    producer_name: str
    producer_component: str | None = None
    producer_version: str | None = None
    source_name: str | None = None
    source_status_id: int | None = None
    event_log_id: int | None = None
    source_event_id: str | None = None
    market_id: str | None = None
    correlation_id: str | None = None
    raw_payload_ref: str | None = None
    generated_from: GeneratedFrom = "unknown"
    lineage: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    @field_validator("signal_id", "neuron_name", "producer_name")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("lineage field is required")
        return normalized

    @field_validator("neuron_name")
    @classmethod
    def normalize_neuron(cls, value: str) -> str:
        return value.strip().lower()

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SignalProducer(BaseModel):
    producer_name: str
    producer_component: str
    neuron_name: str
    source_name: str | None = None
    enabled: bool = True
    expected_signal_types: list[str] = Field(default_factory=list)
    description: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
