from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.external_raw_event import ExternalRawEventContract
from app.repositories.external_raw_events_repository import ExternalRawEventsRepository


class ExternalRawEventRecorder:
    def __init__(self, repository: ExternalRawEventsRepository | None = None) -> None:
        self._repository = repository or ExternalRawEventsRepository()

    def record(self, conn: Connection, contract: ExternalRawEventContract) -> None:
        self._repository.insert(conn, contract)
