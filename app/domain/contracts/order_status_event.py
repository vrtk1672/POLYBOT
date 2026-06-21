from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class OrderStatusEventContract:
    id: str
    order_id: str
    event_at: datetime
    old_status: str | None
    new_status: str
    source: str
    reason: str | None
    exchange_status: str | None
    raw_payload: dict[str, object] = field(default_factory=dict)
