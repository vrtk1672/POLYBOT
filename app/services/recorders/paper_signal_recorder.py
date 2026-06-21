from __future__ import annotations

from app.domain.contracts.paper_signal import PaperSignalContract
from app.repositories.paper_signals_repository import PaperSignalsRepository


class PaperSignalRecorder:
    def __init__(self, repository: PaperSignalsRepository | None = None) -> None:
        self._repository = repository or PaperSignalsRepository()

    def record_many(self, conn, signals: list[PaperSignalContract]) -> None:
        self._repository.upsert_many(conn, signals)
