from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BucketAllocationContract:
    id: str
    bucket_allocation_run_id: str
    market_id: str
    trade_classification_id: str
    primary_trade_type: str
    assigned_bucket_class: str
    bucket_target_fraction: float
    bucket_cap_fraction: float
    deployment_fraction: float
    occupancy_status: str
    deployability_class: str
    allocation_reason_codes_json: list[str] = field(default_factory=list)
    allocation_reason_text: str = ""
    explanation_json: dict[str, object] = field(default_factory=dict)
    allocator_version: str = ""
