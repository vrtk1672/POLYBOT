from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class MarketSnapshotContract:
    cycle_id: str
    market_id: str
    event_id: str | None
    question: str
    slug: str | None
    captured_at: datetime
    yes_price: float | None
    no_price: float | None
    last_trade_price: float | None
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    tick_size: float | None
    liquidity: float | None
    volume: float | None
    volume_24h: float | None
    open_interest: float | None
    comment_count: int | None
    competitive: float | None
    neg_risk: bool | None
    orderbook_enabled: bool | None
    accepting_orders: bool
    time_to_close_seconds: int | None
    raw_payload: dict[str, object] = field(default_factory=dict)
