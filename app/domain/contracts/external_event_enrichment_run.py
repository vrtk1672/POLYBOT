from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class ExternalEventEnrichmentRunOpenContract:
    id: str
    intelligence_ingestion_run_id: str | None
    source_type: str
    source_ref: str | None
    status: str
    enrichment_version: str
    started_at: datetime
    input_count: int
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ExternalEventEnrichmentRunCloseContract:
    id: str
    status: str
    ended_at: datetime
    success_count: int
    failure_count: int
    metadata_json: dict[str, object] = field(default_factory=dict)
