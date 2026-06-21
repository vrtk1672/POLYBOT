from __future__ import annotations

from app.domain.contracts.rejection import RejectionLedgerContract
from app.repositories.rejection_ledger_repository import RejectionLedgerRepository


class RejectionRecorder:
    def __init__(self, repository: RejectionLedgerRepository | None = None) -> None:
        self._repository = repository or RejectionLedgerRepository()

    def record_many(self, conn, rejections: list[RejectionLedgerContract]) -> None:
        self._repository.upsert_many(conn, rejections)
