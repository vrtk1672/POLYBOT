from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class ShadowRunOpenContract:
    id: str
    cycle_id: str | None
    mode: str
    started_at: datetime
    status: str
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ShadowRunCloseContract:
    id: str
    ended_at: datetime
    status: str
    markets_seen_count: int
    markets_ranked_count: int
    candidates_selected_count: int
    shadow_orders_count: int
    metadata_json: dict[str, object] = field(default_factory=dict)
