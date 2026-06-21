from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.whale_scoring_run import WhaleScoringRunCloseContract, WhaleScoringRunOpenContract
from app.repositories.whale_scoring_runs_repository import WhaleScoringRunsRepository


class WhaleScoringRunRecorder:
    def __init__(self, repository: WhaleScoringRunsRepository | None = None) -> None:
        self._repository = repository or WhaleScoringRunsRepository()

    def open_run(self, conn: Connection, contract: WhaleScoringRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: WhaleScoringRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
