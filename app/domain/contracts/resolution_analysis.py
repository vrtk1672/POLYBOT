from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ResolutionAnalysisContract:
    id: str
    resolution_analysis_run_id: str
    interpretation_id: str
    market_link_candidate_id: str
    market_id: str
    market_question: str
    raw_context_json: dict[str, object]
    resolution_summary: str | None
    wording_clarity_score: float | None
    ambiguity_risk_score: float | None
    resolution_mismatch_risk: float | None
    resolution_confidence_score: float | None
    direct_fit_class: str | None
    usable_now_class: str | None
    explanation_json: dict[str, object] = field(default_factory=dict)
    status: str = "SUCCESS"
    error_text: str | None = None
    analyzer_version: str = ""
    prompt_version: str = ""
    model_name: str = ""
