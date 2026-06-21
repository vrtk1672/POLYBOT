from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.whale_profile_run import WhaleProfileRunCloseContract, WhaleProfileRunOpenContract
from app.repositories.whale_profile_runs_repository import WhaleProfileRunsRepository


class WhaleProfileRunRecorder:
    def __init__(self, repository: WhaleProfileRunsRepository | None = None) -> None:
        self._repository = repository or WhaleProfileRunsRepository()

    def open_run(self, conn: Connection, contract: WhaleProfileRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: WhaleProfileRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
