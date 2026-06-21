from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class WhaleRegistryEntryContract:
    id: str
    wallet_address: str
    first_seen_at: datetime
    last_seen_at: datetime
    total_events: int
    last_market_id: str | None
    last_event_direction_class: str | None
    registry_status: str
    metadata_json: dict[str, object] = field(default_factory=dict)
