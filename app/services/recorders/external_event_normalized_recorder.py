from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.external_event_normalized import ExternalEventNormalizedContract
from app.repositories.external_events_normalized_repository import ExternalEventsNormalizedRepository


class ExternalEventNormalizedRecorder:
    def __init__(self, repository: ExternalEventsNormalizedRepository | None = None) -> None:
        self._repository = repository or ExternalEventsNormalizedRepository()

    def record(self, conn: Connection, contract: ExternalEventNormalizedContract) -> None:
        self._repository.insert(conn, contract)
