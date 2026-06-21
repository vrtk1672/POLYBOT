from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExitAdvisoryRecordContract:
    id: str
    exit_advisory_run_id: str
    market_id: str
    invalidation_policy_record_id: str
    exposure_type: str
    exposure_ref_id: str
    advisory_action_class: str
    advisory_priority_class: str
    advisory_reason_codes_json: list[str] = field(default_factory=list)
    advisory_reason_text: str = ""
    explanation_json: dict[str, object] = field(default_factory=dict)
    advisory_version: str = ""
