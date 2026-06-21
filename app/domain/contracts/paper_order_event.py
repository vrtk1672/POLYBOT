from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class PaperOrderEventContract:
    id: str
    paper_order_id: str
    event_at: datetime
    old_status: str | None
    new_status: str
    reason_code: str
    reason_text: str
    payload_json: dict[str, object] = field(default_factory=dict)
