from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class PaperOrderContract:
    id: str
    paper_run_id: str
    paper_signal_id: str
    cycle_id: str | None
    market_id: str
    intended_outcome: str
    action: str
    intended_price: float
    intended_size: float
    notional: float
    status: str
    fill_ratio: float
    filled_size: float
    remaining_size: float
    avg_fill_price: float | None
    min_size_check_passed: bool
    stale_at: datetime | None
    payload_json: dict[str, object] = field(default_factory=dict)
