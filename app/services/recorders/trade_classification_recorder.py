from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.trade_classification import TradeClassificationContract
from app.repositories.trade_classifications_repository import TradeClassificationsRepository


class TradeClassificationRecorder:
    def __init__(self, repository: TradeClassificationsRepository | None = None) -> None:
        self._repository = repository or TradeClassificationsRepository()

    def record(self, conn: Connection, contract: TradeClassificationContract) -> None:
        self._repository.insert(conn, contract)
