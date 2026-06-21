from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CognitionHandoffCandidateContract:
    id: str
    cognition_handoff_run_id: str
    external_event_id: str
    external_event_enrichment_id: str
    intelligence_source_id: str
    handoff_decision_class: str | None
    handoff_priority_class: str | None
    handoff_reason_code: str | None
    handoff_reason_text: str | None
    topic_class: str | None
    usability_hint_class: str | None
    novelty_hint_class: str | None
    contradiction_hint_class: str | None
    trust_weight_snapshot: float
    handoff_payload_json: dict[str, object] = field(default_factory=dict)
    linked_interpretation_run_id: str | None = None
    linked_interpretation_id: str | None = None
    status: str = "SUCCESS"
    error_text: str | None = None
    handoff_version: str = ""
