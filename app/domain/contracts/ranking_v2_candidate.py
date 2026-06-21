from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RankingV2CandidateContract:
    id: str
    ranking_v2_run_id: str
    market_id: str
    cycle_id: str | None
    market_snapshot_id: int | None
    decision_id: str | None
    cognition_summary_id: str | None
    whale_market_score_id: str | None
    trade_classification_id: str | None
    bucket_allocation_id: str | None
    total_rank_score: float
    factor_scores_json: dict[str, object] = field(default_factory=dict)
    rank_position: int = 0
    rank_tier_class: str = "REJECT"
    rank_reason_codes_json: list[str] = field(default_factory=list)
    rank_reason_text: str = ""
    explanation_json: dict[str, object] = field(default_factory=dict)
    ranking_version: str = ""
