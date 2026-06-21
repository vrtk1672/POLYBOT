from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class CognitionHandoffRunOpenContract:
    id: str
    external_event_enrichment_run_id: str | None
    source_type: str
    source_ref: str | None
    status: str
    handoff_version: str
    started_at: datetime
    input_count: int
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class CognitionHandoffRunCloseContract:
    id: str
    status: str
    ended_at: datetime
    sent_count: int
    held_count: int
    skipped_count: int
    failure_count: int
    metadata_json: dict[str, object] = field(default_factory=dict)
