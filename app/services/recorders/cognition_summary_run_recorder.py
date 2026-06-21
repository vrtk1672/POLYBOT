from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.cognition_summary_run import (
    CognitionSummaryRunCloseContract,
    CognitionSummaryRunOpenContract,
)
from app.repositories.cognition_summary_runs_repository import CognitionSummaryRunsRepository


class CognitionSummaryRunRecorder:
    def __init__(self, repository: CognitionSummaryRunsRepository | None = None) -> None:
        self._repository = repository or CognitionSummaryRunsRepository()

    def open_run(self, conn: Connection, contract: CognitionSummaryRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: CognitionSummaryRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
