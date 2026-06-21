from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class ExternalEventNormalizedContract:
    id: str
    external_raw_event_id: str
    intelligence_source_id: str
    normalized_title: str
    normalized_summary: str
    published_at: datetime | None
    canonical_url: str | None
    canonical_hash: str
    event_language: str | None
    source_category: str
    trust_weight_snapshot: float
    dedupe_key: str
    normalization_version: str
    status: str
    metadata_json: dict[str, object] = field(default_factory=dict)
