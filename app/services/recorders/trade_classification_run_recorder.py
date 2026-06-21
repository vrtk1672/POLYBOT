from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.trade_classification_run import (
    TradeClassificationRunCloseContract,
    TradeClassificationRunOpenContract,
)
from app.repositories.trade_classification_runs_repository import TradeClassificationRunsRepository


class TradeClassificationRunRecorder:
    def __init__(self, repository: TradeClassificationRunsRepository | None = None) -> None:
        self._repository = repository or TradeClassificationRunsRepository()

    def open_run(self, conn: Connection, contract: TradeClassificationRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: TradeClassificationRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
