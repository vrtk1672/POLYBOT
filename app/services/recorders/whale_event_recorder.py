from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.whale_event import WhaleEventContract
from app.repositories.whale_events_repository import WhaleEventsRepository


class WhaleEventRecorder:
    def __init__(self, repository: WhaleEventsRepository | None = None) -> None:
        self._repository = repository or WhaleEventsRepository()

    def record(self, conn: Connection, contract: WhaleEventContract) -> None:
        self._repository.insert(conn, contract)
