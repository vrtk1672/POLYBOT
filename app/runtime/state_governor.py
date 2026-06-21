from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.runtime_state_repository import RuntimeStateRepository
from app.runtime.contracts import RuntimeState
from app.runtime.mode_manager import ModeManager
from app.runtime.modes import RuntimeAction, RuntimeMode, get_permissions_for_mode, parse_runtime_action, parse_runtime_mode
from app.runtime.runtime_errors import RuntimeModeTransitionDenied, RuntimePermissionDenied, RuntimeStateUnavailable
from app.runtime.system_power import SystemPower


class StateGovernor:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: RuntimeStateRepository | None = None,
        mode_manager: ModeManager | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or RuntimeStateRepository()
        self._mode_manager = mode_manager or ModeManager()

    def get_current_state(self) -> RuntimeState:
        if not self._factory.enabled:
            raise RuntimeStateUnavailable("runtime state DB is not enabled")
        try:
            with self._factory.connect() as conn:
                state = self._repository.get_current_state(conn)
        except Exception as exc:
            raise RuntimeStateUnavailable("runtime state cannot be loaded") from exc
        if state is None:
            return self.ensure_initial_state()
        return state

    def ensure_initial_state(self) -> RuntimeState:
        if not self._factory.enabled:
            raise RuntimeStateUnavailable("runtime state DB is not enabled")
        try:
            with self._factory.connect() as conn, conn.transaction():
                return self._repository.initialize_if_missing(conn)
        except Exception as exc:
            raise RuntimeStateUnavailable("runtime state cannot be initialized") from exc

    def get_permissions(self):
        state = self.get_current_state()
        permissions = get_permissions_for_mode(state.current_mode)
        if state.system_power == SystemPower.OFF:
            return get_permissions_for_mode(RuntimeMode.KILL)
        if state.kill_switch_active:
            return get_permissions_for_mode(RuntimeMode.KILL)
        if state.cooldown_active and state.current_mode != RuntimeMode.COOLDOWN:
            return get_permissions_for_mode(RuntimeMode.COOLDOWN)
        return permissions

    def request_mode_change(
        self,
        to_mode: RuntimeMode | str,
        *,
        actor: str,
        reason: str,
        metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
        action: str = "REQUEST_MODE_CHANGE",
    ) -> RuntimeState:
        metadata = metadata or {}
        current = self.get_current_state()
        target = parse_runtime_mode(to_mode)
        result = self._mode_manager.evaluate_transition(
            from_mode=current.current_mode,
            to_mode=target,
            actor=actor,
            reason=reason,
            metadata=metadata,
        )
        if not result.allowed:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.insert_history(
                    conn,
                    from_mode=current.current_mode,
                    to_mode=target,
                    action=action,
                    reason=reason or "<missing>",
                    actor=actor or "<missing>",
                    allowed=False,
                    blocked_reason=result.blocked_reason,
                    correlation_id=correlation_id,
                    metadata={**metadata, "transition": result.to_dict()},
                )
            raise RuntimeModeTransitionDenied(result.blocked_reason or "mode transition blocked")
        with self._factory.connect() as conn, conn.transaction():
            self._repository.insert_history(
                conn,
                from_mode=current.current_mode,
                to_mode=target,
                action=action,
                reason=reason or "<missing>",
                actor=actor or "<missing>",
                allowed=result.allowed,
                blocked_reason=result.blocked_reason,
                correlation_id=correlation_id,
                metadata={**metadata, "transition": result.to_dict()},
            )
            return self._repository.update_state(
                conn,
                current_mode=target,
                previous_mode=current.current_mode,
                reason=reason,
                actor=actor,
                correlation_id=correlation_id,
                metadata=metadata,
            )

    def activate_kill(
        self,
        *,
        actor: str,
        reason: str,
        metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> RuntimeState:
        return self.request_mode_change(
            RuntimeMode.KILL,
            actor=actor,
            reason=reason,
            metadata=metadata,
            correlation_id=correlation_id,
            action="ACTIVATE_KILL",
        )

    def resume_from_kill(
        self,
        *,
        actor: str,
        reason: str,
        target_mode: RuntimeMode | str = RuntimeMode.DATA_ONLY,
        metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> RuntimeState:
        return self.request_mode_change(
            target_mode,
            actor=actor,
            reason=reason,
            metadata=metadata,
            correlation_id=correlation_id,
            action="RESUME_FROM_KILL",
        )

    def enter_cooldown(
        self,
        *,
        actor: str,
        reason: str,
        metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> RuntimeState:
        return self.request_mode_change(
            RuntimeMode.COOLDOWN,
            actor=actor,
            reason=reason,
            metadata=metadata,
            correlation_id=correlation_id,
            action="ENTER_COOLDOWN",
        )

    def can_execute(self, action_type: RuntimeAction | str, metadata: dict[str, object] | None = None) -> bool:
        try:
            action = parse_runtime_action(action_type)
            state = self.get_current_state()
            permissions = self.get_permissions()
        except Exception:
            return False
        if state.current_mode == RuntimeMode.ATTACK_MODE and action == RuntimeAction.USE_ATTACK_ENGINE:
            return state.attack_mode_active and state.metadata_json.get("governor_approved") is True
        if state.system_power == SystemPower.OFF:
            return False
        return permissions.allows(action, metadata)

    def assert_can_execute(self, action_type: RuntimeAction | str, metadata: dict[str, object] | None = None) -> None:
        action = parse_runtime_action(action_type)
        if not self.can_execute(action, metadata):
            raise RuntimePermissionDenied(f"{action.value} is blocked by current runtime mode")
