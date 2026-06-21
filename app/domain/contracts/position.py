from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class PositionContract:
    id: str
    market_id: str
    side: str
    size: float
    avg_entry: float | None
    current_status: str
    unrealized: float
    realized: float
    thesis_state: str
    invalidation_state: str
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
