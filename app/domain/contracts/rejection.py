from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RejectionLedgerContract:
    id: str
    cycle_id: str
    market_id: str
    stage: str
    reason_code: str
    reason_text: str
    payload: dict[str, object] = field(default_factory=dict)
