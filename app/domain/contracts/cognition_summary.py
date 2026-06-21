from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CognitionSummaryContract:
    id: str
    cognition_summary_run_id: str
    interpretation_id: str
    market_link_candidate_id: str
    resolution_analysis_id: str
    invalidation_reasoning_id: str
    market_id: str
    market_question: str
    event_summary_snapshot: str
    raw_context_json: dict[str, object]
    narration_summary: str | None
    concise_narration_text: str | None
    cognition_conclusion_class: str | None
    overall_confidence_score: float | None
    caution_score: float | None
    usability_class: str | None
    recommended_operator_focus: str | None
    evidence_json: dict[str, object] = field(default_factory=dict)
    status: str = "SUCCESS"
    error_text: str | None = None
    narrator_version: str = ""
    prompt_version: str = ""
    model_name: str = ""
