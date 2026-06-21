from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RunArtifactContract:
    id: str
    cycle_id: str | None
    artifact_type: str
    artifact_scope: str
    path: str
    checksum: str
    metadata_json: dict[str, object] = field(default_factory=dict)
