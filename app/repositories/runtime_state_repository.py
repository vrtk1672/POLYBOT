from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeMode, parse_runtime_mode
from app.runtime.system_power import SystemPower, parse_system_power


class RuntimeStateRepository:
    def get_current_state(self, conn: Connection) -> RuntimeState | None:
        row = conn.execute(
            """
            SELECT *
            FROM system_state
            WHERE state_status = 'ACTIVE'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return _state_from_row(row) if row is not None else None

    def initialize_if_missing(
        self,
        conn: Connection,
        *,
        actor: str = "runtime_startup",
        reason: str = "safe startup default",
        correlation_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> RuntimeState:
        current = self.get_current_state(conn)
        if current is not None:
            return current
        conn.execute(
            """
            INSERT INTO system_state (
                current_mode, previous_mode, state_status, kill_switch_active,
                cooldown_active, attack_mode_active, reason, actor, correlation_id,
                metadata_json
            )
            VALUES ('DATA_ONLY', NULL, 'ACTIVE', false, false, false, %s, %s, %s, %s)
            """,
            (reason, actor, correlation_id, Jsonb(metadata or {"safe_startup": True})),
        )
        self.insert_history(
            conn,
            from_mode=None,
            to_mode=RuntimeMode.DATA_ONLY,
            action="INITIALIZE",
            reason=reason,
            actor=actor,
            allowed=True,
            correlation_id=correlation_id,
            metadata=metadata or {"safe_startup": True},
        )
        state = self.get_current_state(conn)
        assert state is not None
        return state

    def update_state(
        self,
        conn: Connection,
        *,
        current_mode: RuntimeMode,
        previous_mode: RuntimeMode | None,
        reason: str,
        actor: str,
        correlation_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> RuntimeState:
        metadata = metadata or {}
        kill = current_mode == RuntimeMode.KILL
        cooldown = current_mode == RuntimeMode.COOLDOWN
        attack = current_mode == RuntimeMode.ATTACK_MODE
        existing = self.get_current_state(conn)
        if existing is None:
            conn.execute(
                """
                INSERT INTO system_state (
                    current_mode, previous_mode, state_status, kill_switch_active,
                    cooldown_active, attack_mode_active, reason, actor, correlation_id,
                    metadata_json
                )
                VALUES (%s, %s, 'ACTIVE', %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    current_mode.value,
                    previous_mode.value if previous_mode else None,
                    kill,
                    cooldown,
                    attack,
                    reason,
                    actor,
                    correlation_id,
                    Jsonb(metadata),
                ),
            )
        else:
            conn.execute(
                """
                UPDATE system_state
                SET current_mode = %s,
                    previous_mode = %s,
                    kill_switch_active = %s,
                    cooldown_active = %s,
                    attack_mode_active = %s,
                    reason = %s,
                    actor = %s,
                    correlation_id = %s,
                    last_transition_at = now(),
                    updated_at = now(),
                    metadata_json = %s
                WHERE id = (
                    SELECT id FROM system_state
                    WHERE state_status = 'ACTIVE'
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                )
                """,
                (
                    current_mode.value,
                    previous_mode.value if previous_mode else None,
                    kill,
                    cooldown,
                    attack,
                    reason,
                    actor,
                    correlation_id,
                    Jsonb(metadata),
                ),
            )
        state = self.get_current_state(conn)
        assert state is not None
        return state

    def insert_history(
        self,
        conn: Connection,
        *,
        from_mode: RuntimeMode | None,
        to_mode: RuntimeMode,
        action: str,
        reason: str,
        actor: str,
        allowed: bool,
        blocked_reason: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO system_state_history (
                from_mode, to_mode, action, reason, actor, allowed, blocked_reason,
                correlation_id, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                from_mode.value if from_mode else None,
                to_mode.value,
                action,
                reason,
                actor,
                allowed,
                blocked_reason,
                correlation_id,
                Jsonb(metadata or {}),
            ),
        )

    def list_history(self, conn: Connection, limit: int = 50) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM system_state_history
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


def _state_from_row(row: dict[str, object]) -> RuntimeState:
    previous = row.get("previous_mode")
    metadata = row.get("metadata_json")
    power = row.get("system_power") or "ON"
    return RuntimeState(
        current_mode=parse_runtime_mode(str(row["current_mode"])),
        previous_mode=parse_runtime_mode(str(previous)) if previous else None,
        state_status=str(row["state_status"]),
        kill_switch_active=bool(row["kill_switch_active"]),
        cooldown_active=bool(row["cooldown_active"]),
        attack_mode_active=bool(row["attack_mode_active"]),
        reason=str(row["reason"]),
        actor=str(row["actor"]),
        correlation_id=str(row["correlation_id"]) if row.get("correlation_id") is not None else None,
        last_transition_at=row.get("last_transition_at"),
        metadata_json=dict(metadata) if isinstance(metadata, dict) else {},
        system_power=parse_system_power(str(power)),
        system_power_actor=str(row["system_power_actor"]) if row.get("system_power_actor") is not None else None,
        system_power_reason=str(row["system_power_reason"]) if row.get("system_power_reason") is not None else None,
        system_power_correlation_id=str(row["system_power_correlation_id"]) if row.get("system_power_correlation_id") is not None else None,
        system_power_transition_at=row.get("system_power_transition_at"),
    )


class SystemPowerRepository:
    def get_current_power_row(self, conn: Connection) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT current_mode, kill_switch_active, system_power,
                   system_power_actor, system_power_reason,
                   system_power_correlation_id, system_power_transition_at,
                   metadata_json
            FROM system_state
            WHERE state_status = 'ACTIVE'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()

    def update_power(
        self,
        conn: Connection,
        *,
        old_power: SystemPower | None,
        new_power: SystemPower,
        actor: str,
        reason: str,
        correlation_id: str | None,
        transition_id: str,
        result: str = "OK",
        error_message: str | None = None,
    ) -> dict[str, object]:
        conn.execute(
            """
            UPDATE system_state
            SET system_power = %s,
                system_power_actor = %s,
                system_power_reason = %s,
                system_power_correlation_id = %s,
                system_power_transition_at = now(),
                updated_at = now()
            WHERE id = (
                SELECT id FROM system_state
                WHERE state_status = 'ACTIVE'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
            )
            """,
            (new_power.value, actor, reason, correlation_id),
        )
        self.insert_transition(
            conn,
            old_power=old_power,
            new_power=new_power,
            actor=actor,
            reason=reason,
            correlation_id=correlation_id,
            transition_id=transition_id,
            result=result,
            error_message=error_message,
        )
        row = self.get_current_power_row(conn)
        assert row is not None
        return dict(row)

    def insert_transition(
        self,
        conn: Connection,
        *,
        old_power: SystemPower | None,
        new_power: SystemPower,
        actor: str,
        reason: str,
        correlation_id: str | None,
        transition_id: str,
        result: str,
        error_message: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO system_power_transitions (
                transition_id, old_power, new_power, actor, reason,
                correlation_id, result, error_message
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                transition_id,
                old_power.value if old_power else None,
                new_power.value,
                actor,
                reason,
                correlation_id,
                result,
                error_message,
            ),
        )

    def latest_transition(self, conn: Connection) -> dict[str, object] | None:
        row = conn.execute(
            """
            SELECT *
            FROM system_power_transitions
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def list_transitions(self, conn: Connection, limit: int = 50) -> list[dict[str, object]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM system_power_transitions
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]
