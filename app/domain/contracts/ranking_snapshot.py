from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RankingSnapshotContract:
    cycle_id: str
    market_snapshot_id: int
    market_id: str
    rank_position: int | None
    base_score: float | None
    adaptive_rank: float | None
    selected_flag: bool
    eligible_flag: bool
    reject_reason: str | None
    ranking_breakdown: dict[str, object] = field(default_factory=dict)
    recommendation_action: str | None = None
    recommendation_confidence: float | None = None
    recommendation_reason: str | None = None
