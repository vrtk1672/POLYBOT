from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.cognition_summary import CognitionSummaryContract
from app.repositories.cognition_summaries_repository import CognitionSummariesRepository


class CognitionSummaryRecorder:
    def __init__(self, repository: CognitionSummariesRepository | None = None) -> None:
        self._repository = repository or CognitionSummariesRepository()

    def record(self, conn: Connection, contract: CognitionSummaryContract) -> None:
        self._repository.insert(conn, contract)
