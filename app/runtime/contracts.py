from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from app.runtime.modes import RuntimeMode, RuntimePermissions
from app.runtime.system_power import SystemPower


@dataclass(slots=True)
class RuntimeState:
    current_mode: RuntimeMode
    previous_mode: RuntimeMode | None
    state_status: str
    kill_switch_active: bool
    cooldown_active: bool
    attack_mode_active: bool
    reason: str
    actor: str
    correlation_id: str | None = None
    last_transition_at: datetime | str | None = None
    metadata_json: dict[str, object] = field(default_factory=dict)
    system_power: SystemPower = SystemPower.ON
    system_power_actor: str | None = None
    system_power_reason: str | None = None
    system_power_correlation_id: str | None = None
    system_power_transition_at: datetime | str | None = None

    def to_dict(self) -> dict[str, object]:
        output = asdict(self)
        output["current_mode"] = self.current_mode.value
        output["previous_mode"] = self.previous_mode.value if self.previous_mode else None
        output["system_power"] = self.system_power.value
        if isinstance(self.last_transition_at, datetime):
            output["last_transition_at"] = self.last_transition_at.isoformat()
        if isinstance(self.system_power_transition_at, datetime):
            output["system_power_transition_at"] = self.system_power_transition_at.isoformat()
        return output


@dataclass(frozen=True, slots=True)
class ModeTransitionResult:
    allowed: bool
    from_mode: RuntimeMode | None
    to_mode: RuntimeMode | None
    blocked_reason: str | None = None
    required_metadata: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "from_mode": self.from_mode.value if self.from_mode else None,
            "to_mode": self.to_mode.value if self.to_mode else None,
            "blocked_reason": self.blocked_reason,
            "required_metadata": list(self.required_metadata),
            "warnings": list(self.warnings),
        }


@dataclass(slots=True)
class RuntimeStateResponse:
    state: RuntimeState
    permissions: RuntimePermissions

    def to_dict(self) -> dict[str, object]:
        return {"state": self.state.to_dict(), "permissions": self.permissions.to_dict()}
