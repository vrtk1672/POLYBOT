from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RankingPolicyCandidateContract:
    id: str
    ranking_policy_run_id: str
    market_id: str
    ranking_v2_candidate_id: str
    total_rank_score: float
    rank_position: int
    rank_tier_class: str
    gate_decision_class: str
    gate_priority_class: str
    max_selected_within_run: int
    selection_reason_codes_json: list[str] = field(default_factory=list)
    selection_reason_text: str = ""
    policy_explanation_json: dict[str, object] = field(default_factory=dict)
    policy_version: str = ""
