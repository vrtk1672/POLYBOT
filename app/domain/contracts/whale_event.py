from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class WhaleEventContract:
    id: str
    whale_scan_run_id: str
    wallet_address: str
    market_id: str
    event_timestamp: datetime
    event_direction_class: str
    side_or_outcome: str | None
    size: float
    notional: float | None
    price: float | None
    transaction_ref: str | None
    source_type: str
    source_payload_json: dict[str, object] = field(default_factory=dict)
    detection_reason_code: str = ""
    detection_reason_text: str = ""
