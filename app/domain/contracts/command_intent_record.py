from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CommandIntentRecordContract:
    id: str
    command_intent_run_id: str
    market_id: str
    advisory_resolution_record_id: str
    exit_advisory_record_id: str | None
    exposure_type: str
    exposure_ref_id: str
    command_intent_class: str
    command_priority_class: str
    command_status_class: str
    orchestration_eligibility_class: str
    command_reason_codes_json: list[str] = field(default_factory=list)
    command_reason_text: str = ""
    explanation_json: dict[str, object] = field(default_factory=dict)
    advisory_resolution_version: str | None = None
    command_intent_version: str = ""
