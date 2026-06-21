from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class IntelligenceSourceContract:
    id: str
    source_key: str
    source_name: str
    source_type: str
    base_url: str | None
    category: str
    trust_weight: float
    latency_score: float | None
    noise_score: float | None
    relevance_scope: str | None
    is_enabled: bool
    metadata_json: dict[str, object] = field(default_factory=dict)
