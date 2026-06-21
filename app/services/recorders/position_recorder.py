from __future__ import annotations

from app.domain.contracts.position import PositionContract
from app.repositories.positions_repository import PositionsRepository


class PositionRecorder:
    def __init__(self, repository: PositionsRepository | None = None) -> None:
        self._repository = repository or PositionsRepository()

    def record(self, conn, position: PositionContract) -> None:
        self._repository.upsert(conn, position)
