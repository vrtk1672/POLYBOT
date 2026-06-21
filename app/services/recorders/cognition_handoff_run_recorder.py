from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.cognition_handoff_run import (
    CognitionHandoffRunCloseContract,
    CognitionHandoffRunOpenContract,
)
from app.repositories.cognition_handoff_runs_repository import CognitionHandoffRunsRepository


class CognitionHandoffRunRecorder:
    def __init__(self, repository: CognitionHandoffRunsRepository | None = None) -> None:
        self._repository = repository or CognitionHandoffRunsRepository()

    def open_run(self, conn: Connection, contract: CognitionHandoffRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: CognitionHandoffRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
