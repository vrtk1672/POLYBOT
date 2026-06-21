from __future__ import annotations

from app.domain.contracts.shadow_position import ShadowPositionContract
from app.repositories.shadow_positions_repository import ShadowPositionsRepository


class ShadowPositionRecorder:
    def __init__(self, repository: ShadowPositionsRepository | None = None) -> None:
        self._repository = repository or ShadowPositionsRepository()

    def record(self, conn, position: ShadowPositionContract) -> None:
        self._repository.upsert(conn, position)
