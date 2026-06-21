from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.whale_scan_run import WhaleScanRunCloseContract, WhaleScanRunOpenContract
from app.repositories.whale_scan_runs_repository import WhaleScanRunsRepository


class WhaleScanRunRecorder:
    def __init__(self, repository: WhaleScanRunsRepository | None = None) -> None:
        self._repository = repository or WhaleScanRunsRepository()

    def open_run(self, conn: Connection, contract: WhaleScanRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: WhaleScanRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
