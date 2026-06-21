from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class InvalidationReasoningContract:
    id: str
    invalidation_reasoning_run_id: str
    interpretation_id: str
    market_link_candidate_id: str
    resolution_analysis_id: str
    market_id: str
    market_question: str
    raw_context_json: dict[str, object]
    reasoning_summary: str | None
    thesis_effect_class: str | None
    invalidation_risk_score: float | None
    confidence_degradation_score: float | None
    contradiction_strength_score: float | None
    recommended_monitoring_class: str | None
    advisory_action_class: str | None
    explanation_json: dict[str, object] = field(default_factory=dict)
    status: str = "SUCCESS"
    error_text: str | None = None
    reasoner_version: str = ""
    prompt_version: str = ""
    model_name: str = ""
