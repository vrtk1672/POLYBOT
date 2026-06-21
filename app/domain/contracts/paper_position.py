from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class PaperPositionContract:
    id: str
    paper_run_id: str
    market_id: str
    intended_outcome: str
    size: float
    avg_entry: float | None
    mark_price: float | None
    unrealized: float | None
    realized: float | None
    current_status: str
    thesis_state: str
    invalidation_state: str
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    payload_json: dict[str, object] = field(default_factory=dict)
