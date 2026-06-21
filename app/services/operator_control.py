from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.operator_control_action import OperatorControlActionContract
from app.repositories.operator_control_actions_repository import OperatorControlActionsRepository
from app.runtime.runtime_errors import RuntimeModeTransitionDenied
from app.runtime.state_governor import StateGovernor


@dataclass(slots=True)
class OperatorControlResult:
    action_id: str
    action_class: str
    status_class: str
    message: str
    is_real_control: bool


class OperatorControlService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._actions = OperatorControlActionsRepository()
        self._governor = StateGovernor(connection_factory=self._factory)

    def request_placeholder_action(
        self,
        *,
        action_class: str,
        requested_via: str,
        requested_by: str | None,
        command_text: str | None,
    ) -> OperatorControlResult:
        action_id = str(uuid4())
        message = (
            f"{action_class} was recorded for audit only. "
            "No runtime control seam is wired yet, so no execution state was changed."
        )
        with self._factory.connect() as conn, conn.transaction():
            self._actions.insert(
                conn,
                OperatorControlActionContract(
                    id=action_id,
                    action_class=action_class,
                    requested_via=requested_via,
                    requested_by=requested_by,
                    command_text=command_text,
                    status_class="PLACEHOLDER",
                    reason_text=message,
                    metadata_json={"placeholder": True},
                ),
            )
        return OperatorControlResult(
            action_id=action_id,
            action_class=action_class,
            status_class="PLACEHOLDER",
            message=message,
            is_real_control=False,
        )

    def request_live_cage_action(
        self,
        *,
        action_class: str,
        requested_via: str,
        requested_by: str | None,
        command_text: str | None,
    ) -> OperatorControlResult:
        action_id = str(uuid4())
        normalized_action = action_class.upper()
        if normalized_action == "KILL":
            state = self._governor.activate_kill(
                actor=requested_by or requested_via,
                reason=command_text or "operator kill request",
                metadata={"requested_via": requested_via, "legacy_live_cage_guard": True},
            )
            status_class = "ACTIVE_GUARD"
            message = f"KILL is active in the V2 runtime governor. Current mode: {state.current_mode.value}."
        elif normalized_action == "RESUME":
            try:
                state = self._governor.resume_from_kill(
                    actor=requested_by or requested_via,
                    reason=command_text or "operator resume request",
                    target_mode="DATA_ONLY",
                    metadata={"requested_via": requested_via, "legacy_live_cage_guard": True},
                )
                status_class = "RELEASED_GUARD"
                message = f"Runtime resumed to {state.current_mode.value}. Env guards still remain in force."
            except RuntimeModeTransitionDenied as exc:
                status_class = "BLOCKED"
                message = f"RESUME blocked by V2 runtime governor: {exc}"
        else:
            status_class = "PLACEHOLDER"
            message = f"{normalized_action} is not a live cage action."
        with self._factory.connect() as conn, conn.transaction():
            self._actions.insert(
                conn,
                OperatorControlActionContract(
                    id=action_id,
                    action_class=normalized_action,
                    requested_via=requested_via,
                    requested_by=requested_by,
                    command_text=command_text,
                    status_class=status_class,
                    reason_text=message,
                    metadata_json={"live_cage_guard": normalized_action in {"KILL", "RESUME"}},
                ),
            )
        return OperatorControlResult(
            action_id=action_id,
            action_class=normalized_action,
            status_class=status_class,
            message=message,
            is_real_control=normalized_action in {"KILL", "RESUME"},
        )

    def request_cooldown_action(
        self,
        *,
        requested_via: str,
        requested_by: str | None,
        command_text: str | None,
    ) -> OperatorControlResult:
        action_id = str(uuid4())
        state = self._governor.enter_cooldown(
            actor=requested_by or requested_via,
            reason=command_text or "operator pause request",
            metadata={"requested_via": requested_via},
        )
        message = f"Runtime entered {state.current_mode.value}. New entries are blocked by mode."
        with self._factory.connect() as conn, conn.transaction():
            self._actions.insert(
                conn,
                OperatorControlActionContract(
                    id=action_id,
                    action_class="PAUSE",
                    requested_via=requested_via,
                    requested_by=requested_by,
                    command_text=command_text,
                    status_class="ACTIVE_GUARD",
                    reason_text=message,
                    metadata_json={"runtime_mode": state.current_mode.value},
                ),
            )
        return OperatorControlResult(
            action_id=action_id,
            action_class="PAUSE",
            status_class="ACTIVE_GUARD",
            message=message,
            is_real_control=True,
        )

    def list_recent_actions(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._actions.list_recent(conn, limit)
        return [dict(row) for row in rows]
