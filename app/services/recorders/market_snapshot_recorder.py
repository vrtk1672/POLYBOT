from __future__ import annotations

from app.domain.contracts.market_snapshot import MarketSnapshotContract
from app.repositories.market_snapshots_repository import MarketSnapshotsRepository


class MarketSnapshotRecorder:
    def __init__(self, repository: MarketSnapshotsRepository | None = None) -> None:
        self._repository = repository or MarketSnapshotsRepository()

    def record_many(self, conn, snapshots: list[MarketSnapshotContract]) -> dict[str, int]:
        return self._repository.upsert_many(conn, snapshots)
