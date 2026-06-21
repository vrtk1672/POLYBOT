from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class PositionEventContract:
    id: str
    position_id: str
    event_type: str
    event_at: datetime
    reason: str
    details: dict[str, object] = field(default_factory=dict)
