from __future__ import annotations

from app.domain.contracts.shadow_order import ShadowOrderContract
from app.repositories.shadow_orders_repository import ShadowOrdersRepository


class ShadowOrderRecorder:
    def __init__(self, repository: ShadowOrdersRepository | None = None) -> None:
        self._repository = repository or ShadowOrdersRepository()

    def record(self, conn, order: ShadowOrderContract) -> None:
        self._repository.upsert(conn, order)
