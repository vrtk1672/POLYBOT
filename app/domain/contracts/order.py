from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class LiveOrderContract:
    id: str
    client_order_id: str
    cycle_id: str | None
    decision_id: str | None
    market_id: str
    token_id: str
    side: str
    action: str
    price: float
    size: float
    notional: float
    status: str
    exchange_status: str | None
    exchange_order_id: str | None
    raw_request: dict[str, object] = field(default_factory=dict)
    raw_response: dict[str, object] = field(default_factory=dict)
    error_text: str | None = None
