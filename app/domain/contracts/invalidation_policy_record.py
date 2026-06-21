from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class InvalidationPolicyRecordContract:
    id: str
    invalidation_policy_run_id: str
    market_id: str
    cycle_id: str | None
    ranking_policy_candidate_id: str | None
    cognition_summary_id: str | None
    invalidation_reasoning_id: str | None
    trade_classification_id: str | None
    bucket_allocation_id: str | None
    invalidation_state_class: str
    exit_policy_class: str
    invalidation_severity_score: float
    exit_urgency_score: float
    deployment_gate_effect: str
    policy_reason_codes_json: list[str] = field(default_factory=list)
    policy_reason_text: str = ""
    explanation_json: dict[str, object] = field(default_factory=dict)
    policy_version: str = ""
