from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.external_event_enrichment import ExternalEventEnrichmentContract
from app.repositories.external_event_enrichments_repository import ExternalEventEnrichmentsRepository


class ExternalEventEnrichmentRecorder:
    def __init__(self, repository: ExternalEventEnrichmentsRepository | None = None) -> None:
        self._repository = repository or ExternalEventEnrichmentsRepository()

    def record(self, conn: Connection, contract: ExternalEventEnrichmentContract) -> None:
        self._repository.insert(conn, contract)
