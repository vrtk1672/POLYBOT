from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EventInterpretationContract:
    id: str
    interpretation_run_id: str
    source_type: str
    source_ref: str | None
    status: str
    error_text: str | None
    raw_event_text: str
    raw_event_payload_json: dict[str, object]
    normalized_event_title: str | None
    event_type: str | None
    event_summary: str | None
    certainty_score: float | None
    ambiguity_score: float | None
    novelty_score: float | None
    directness_class: str | None
    directness_score: float | None
    contradiction_risk: float | None
    affected_market_candidates_json: list[dict[str, object]]
    affected_outcomes_json: list[object]
    recommended_action_class: str | None
    explanation_json: dict[str, object] = field(default_factory=dict)
    prompt_version: str = ""
    model_name: str = ""
