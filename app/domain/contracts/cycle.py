from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class CycleOpenContract:
    id: str
    started_at: datetime
    status: str
    mode: str
    trigger_source: str
    session_id: str | None
    top_n: int
    pages_requested: int | None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class CycleCloseContract:
    id: str
    status: str
    completed_at: datetime
    markets_fetched_count: int
    markets_scored_count: int
    markets_ranked_count: int
    decisions_count: int
    selected_market_id: str | None
    runtime_ms: int | None
    last_error: str | None = None
