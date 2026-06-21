from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.repositories.runtime_cycle_repository import RuntimeCycleRepository
from app.runtime.modes import RuntimeAction, RuntimeMode
from app.runtime.runtime_errors import RuntimePermissionDenied, RuntimeStateUnavailable
from app.runtime.state_governor import StateGovernor


STAGE_ACTIONS: dict[str, RuntimeAction] = {
    "scanner": RuntimeAction.COLLECT_DATA,
    "intelligence": RuntimeAction.RUN_INTELLIGENCE,
    "paper": RuntimeAction.RUN_PAPER_ENGINE,
    "shadow": RuntimeAction.RUN_SHADOW_ENGINE,
    "live": RuntimeAction.RUN_LIVE_ENGINE,
}


class RuntimeCycleOrchestrator:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: RuntimeCycleRepository | None = None,
        governor: StateGovernor | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or RuntimeCycleRepository()
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self.cycle_id: str | None = None
        self.mode: RuntimeMode | None = None

    def start_cycle(self, metadata: dict[str, object] | None = None) -> str | None:
        try:
            state = self._governor.get_current_state()
        except RuntimeStateUnavailable:
            state = None
        self.mode = state.current_mode if state is not None else RuntimeMode.KILL
        self.cycle_id = f"v2-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:10]}"
        if not self._factory.enabled:
            return self.cycle_id
        with self._factory.connect() as conn, conn.transaction():
            self._repository.mark_stale_abandoned(
                conn,
                older_than=datetime.now(UTC) - timedelta(minutes=10),
                reason="runtime_cycle_start_ttl_cleanup",
            )
            self._repository.start_cycle(conn, self.cycle_id, self.mode.value, metadata or {})
            if self.mode == RuntimeMode.KILL:
                self._repository.mark_blocked_by_mode(conn, self.cycle_id)
        return self.cycle_id

    def finish_cycle(
        self,
        *,
        status: str = "COMPLETED",
        error_count: int = 0,
        warning_count: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if not self.cycle_id or not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.finish_cycle(conn, self.cycle_id, status, error_count, warning_count, metadata or {})

    def mark_stage_started(self, stage_name: str) -> None:
        if not self.cycle_id or not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.mark_stage_started(conn, self.cycle_id, stage_name)

    def mark_stage_finished(self, stage_name: str) -> None:
        if not self.cycle_id or not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.mark_stage_finished(conn, self.cycle_id, stage_name)

    def should_run_stage(self, stage_name: str) -> bool:
        action = STAGE_ACTIONS[stage_name.strip().lower()]
        if not self._factory.enabled:
            return action in {RuntimeAction.COLLECT_DATA, RuntimeAction.RUN_INTELLIGENCE}
        return self._governor.can_execute(action)

    def run_stage_guard(self, stage_name: str, action_type: RuntimeAction | str | None = None) -> bool:
        action = action_type or STAGE_ACTIONS[stage_name.strip().lower()]
        if not self._factory.enabled and action in {RuntimeAction.COLLECT_DATA, RuntimeAction.RUN_INTELLIGENCE}:
            return True
        allowed = self._governor.can_execute(action)
        if not allowed:
            if self.cycle_id and self._factory.enabled:
                with self._factory.connect() as conn, conn.transaction():
                    self._repository.mark_blocked_by_mode(conn, self.cycle_id)
            raise RuntimePermissionDenied(f"{stage_name} blocked by runtime mode")
        return True
