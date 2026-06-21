from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class OperatorControlActionContract:
    id: str
    action_class: str
    requested_via: str
    requested_by: str | None
    command_text: str | None
    status_class: str
    reason_text: str
    metadata_json: dict[str, object] = field(default_factory=dict)
