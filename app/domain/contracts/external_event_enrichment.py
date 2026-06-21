from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExternalEventEnrichmentContract:
    id: str
    external_event_enrichment_run_id: str
    external_event_id: str
    intelligence_source_id: str
    normalized_title_snapshot: str
    normalized_summary_snapshot: str
    entities_json: dict[str, object] = field(default_factory=dict)
    topic_class: str | None = None
    subtopic_class: str | None = None
    contradiction_hint_class: str | None = None
    novelty_hint_class: str | None = None
    usability_hint_class: str | None = None
    trust_weight_snapshot: float = 0.0
    enrichment_version: str = ""
    explanation_json: dict[str, object] = field(default_factory=dict)
    status: str = "SUCCESS"
    error_text: str | None = None
