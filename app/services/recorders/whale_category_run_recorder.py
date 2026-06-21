from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.whale_category_run import WhaleCategoryRunCloseContract, WhaleCategoryRunOpenContract
from app.repositories.whale_category_runs_repository import WhaleCategoryRunsRepository


class WhaleCategoryRunRecorder:
    def __init__(self, repository: WhaleCategoryRunsRepository | None = None) -> None:
        self._repository = repository or WhaleCategoryRunsRepository()

    def open_run(self, conn: Connection, contract: WhaleCategoryRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: WhaleCategoryRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
