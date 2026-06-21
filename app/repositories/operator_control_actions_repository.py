from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.operator_control_action import OperatorControlActionContract


class OperatorControlActionsRepository:
    def insert(self, conn: Connection, action: OperatorControlActionContract) -> None:
        conn.execute(
            """
            INSERT INTO operator_control_actions (
                id, action_class, requested_via, requested_by, command_text,
                status_class, reason_text, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                action.id,
                action.action_class,
                action.requested_via,
                action.requested_by,
                action.command_text,
                action.status_class,
                action.reason_text,
                Jsonb(action.metadata_json),
            ),
        )

    def list_recent(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM operator_control_actions
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
