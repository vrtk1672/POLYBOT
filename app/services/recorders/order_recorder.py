from __future__ import annotations

from app.domain.contracts.order import LiveOrderContract
from app.repositories.live_orders_repository import LiveOrdersRepository


class OrderRecorder:
    def __init__(self, repository: LiveOrdersRepository | None = None) -> None:
        self._repository = repository or LiveOrdersRepository()

    def record(self, conn, order: LiveOrderContract) -> None:
        self._repository.upsert(conn, order)
