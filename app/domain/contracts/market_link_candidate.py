from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MarketLinkCandidateContract:
    id: str
    market_link_run_id: str
    interpretation_id: str
    market_id: str
    candidate_source: str
    link_status: str
    relevance_score: float
    directness_class: str | None
    directness_score: float | None
    contradiction_risk: float | None
    affected_outcome: str | None
    usability_class: str
    explanation_json: dict[str, object] = field(default_factory=dict)
    linker_version: str = ""
    prompt_version: str | None = None
    model_name: str | None = None
