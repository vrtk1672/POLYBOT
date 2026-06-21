from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.envelope import EventEnvelope
from app.repositories.event_store_repository import EventStoreRepository


class DeadLetterQueue:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: EventStoreRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or EventStoreRepository()

    def move_to_dlq(
        self,
        envelope: EventEnvelope,
        *,
        consumer_name: str,
        reason: str,
        error_message: str | None = None,
        attempts: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.move_to_dlq(
                conn,
                envelope=envelope,
                consumer_name=consumer_name,
                reason=reason,
                error_message=error_message,
                attempts=attempts,
                metadata=metadata,
            )

    def list_dlq(self, *, status: str = "OPEN", limit: int = 100) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return [dict(row) for row in self._repository.list_dlq(conn, status=status, limit=limit)]

    def mark_dlq_resolved(self, dlq_id: int) -> None:
        self._update_status(dlq_id, "RESOLVED")

    def mark_dlq_ignored(self, dlq_id: int) -> None:
        self._update_status(dlq_id, "IGNORED")

    def mark_dlq_replayed(self, dlq_id: int) -> None:
        self._update_status(dlq_id, "REPLAYED")

    def replay_dlq_item(self, dlq_id: int) -> None:
        self.mark_dlq_replayed(dlq_id)

    def _update_status(self, dlq_id: int, status: str) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.update_dlq_status(conn, dlq_id=dlq_id, status=status)
