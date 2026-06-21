from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class ShadowPositionEventContract:
    id: str
    shadow_position_id: str
    event_at: datetime
    event_type: str
    reason_code: str
    reason_text: str
    payload_json: dict[str, object] = field(default_factory=dict)
