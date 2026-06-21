from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class IntelligenceIngestionRunOpenContract:
    id: str
    intelligence_source_id: str | None
    run_type: str
    status: str
    started_at: datetime
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class IntelligenceIngestionRunCloseContract:
    id: str
    status: str
    ended_at: datetime
    fetched_count: int
    normalized_count: int
    deduped_count: int
    failed_count: int
    metadata_json: dict[str, object] = field(default_factory=dict)
