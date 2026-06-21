from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class ShadowPositionContract:
    id: str
    shadow_run_id: str
    shadow_order_id: str
    market_id: str
    intended_outcome: str | None
    size: float
    avg_entry: float | None
    current_status: str
    mark_price: float | None
    unrealized: float | None
    realized: float | None
    thesis_state: str
    invalidation_state: str
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    payload_json: dict[str, object] = field(default_factory=dict)
