from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AdvisoryResolutionRecordContract:
    id: str
    advisory_resolution_run_id: str
    market_id: str
    cycle_id: str | None
    invalidation_policy_record_id: str | None
    exit_advisory_run_id: str | None
    primary_advisory_action_class: str
    primary_priority_class: str
    action_readiness_class: str
    conflict_status_class: str
    exposure_count: int
    critical_exposure_count: int
    advisory_reason_codes_json: list[str] = field(default_factory=list)
    advisory_reason_text: str = ""
    explanation_json: dict[str, object] = field(default_factory=dict)
    advisory_resolution_version: str = ""
