from __future__ import annotations

from app.domain.contracts.paper_position import PaperPositionContract
from app.repositories.paper_positions_repository import PaperPositionsRepository


class PaperPositionRecorder:
    def __init__(self, repository: PaperPositionsRepository | None = None) -> None:
        self._repository = repository or PaperPositionsRepository()

    def record(self, conn, position: PaperPositionContract) -> None:
        self._repository.upsert(conn, position)
