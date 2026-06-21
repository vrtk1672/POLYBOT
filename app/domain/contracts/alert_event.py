from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class AlertEventContract:
    id: str
    event_class: str
    severity_class: str
    title: str
    body_text: str
    dedupe_key: str | None
    source_ref: str | None
    delivery_status_class: str
    payload_json: dict[str, object] = field(default_factory=dict)
    delivered_at: datetime | None = None
