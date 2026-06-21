from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.intelligence_ingestion_run import (
    IntelligenceIngestionRunCloseContract,
    IntelligenceIngestionRunOpenContract,
)
from app.repositories.intelligence_ingestion_runs_repository import IntelligenceIngestionRunsRepository


class IntelligenceIngestionRunRecorder:
    def __init__(self, repository: IntelligenceIngestionRunsRepository | None = None) -> None:
        self._repository = repository or IntelligenceIngestionRunsRepository()

    def open_run(self, conn: Connection, contract: IntelligenceIngestionRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: IntelligenceIngestionRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
