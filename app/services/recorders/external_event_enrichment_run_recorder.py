from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.external_event_enrichment_run import (
    ExternalEventEnrichmentRunCloseContract,
    ExternalEventEnrichmentRunOpenContract,
)
from app.repositories.external_event_enrichment_runs_repository import (
    ExternalEventEnrichmentRunsRepository,
)


class ExternalEventEnrichmentRunRecorder:
    def __init__(self, repository: ExternalEventEnrichmentRunsRepository | None = None) -> None:
        self._repository = repository or ExternalEventEnrichmentRunsRepository()

    def open_run(self, conn: Connection, contract: ExternalEventEnrichmentRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: ExternalEventEnrichmentRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
