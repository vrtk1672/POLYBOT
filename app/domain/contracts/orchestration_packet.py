from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class OrchestrationPacketContract:
    id: str
    orchestration_gate_run_id: str
    packet_status_class: str
    packet_priority_class: str
    packet_action_count: int
    markets_covered_count: int
    included_command_intent_ids_json: list[str] = field(default_factory=list)
    packet_reason_codes_json: list[str] = field(default_factory=list)
    packet_reason_text: str = ""
    explanation_json: dict[str, object] = field(default_factory=dict)
    orchestration_version: str = ""
