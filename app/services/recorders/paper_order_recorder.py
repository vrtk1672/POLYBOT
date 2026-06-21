from __future__ import annotations

from app.domain.contracts.paper_order import PaperOrderContract
from app.repositories.paper_orders_repository import PaperOrdersRepository


class PaperOrderRecorder:
    def __init__(self, repository: PaperOrdersRepository | None = None) -> None:
        self._repository = repository or PaperOrdersRepository()

    def record(self, conn, order: PaperOrderContract) -> None:
        self._repository.upsert(conn, order)
