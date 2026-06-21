from __future__ import annotations

from app.domain.contracts.decision import DecisionLedgerContract
from app.repositories.decision_ledger_repository import DecisionLedgerRepository


class DecisionLedgerRecorder:
    def __init__(self, repository: DecisionLedgerRepository | None = None) -> None:
        self._repository = repository or DecisionLedgerRepository()

    def record_many(self, conn, decisions: list[DecisionLedgerContract]) -> None:
        self._repository.upsert_many(conn, decisions)
