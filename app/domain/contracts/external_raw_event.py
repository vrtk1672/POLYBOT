from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class ExternalRawEventContract:
    id: str
    intelligence_ingestion_run_id: str
    intelligence_source_id: str
    source_event_id: str | None
    source_url: str | None
    source_published_at: datetime | None
    source_title: str | None
    raw_content_text: str | None
    raw_payload_json: dict[str, object] = field(default_factory=dict)
    raw_hash: str = ""
    fetched_at: datetime | None = None
