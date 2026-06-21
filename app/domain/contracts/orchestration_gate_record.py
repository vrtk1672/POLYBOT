from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class OrchestrationGateRecordContract:
    id: str
    orchestration_gate_run_id: str
    market_id: str
    command_intent_record_id: str
    orchestration_decision_class: str
    orchestration_reason_codes_json: list[str] = field(default_factory=list)
    orchestration_reason_text: str = ""
    gate_explanation_json: dict[str, object] = field(default_factory=dict)
    packet_candidate_id: str | None = None
    orchestration_version: str = ""
