from __future__ import annotations

from app.domain.contracts.ranking_snapshot import RankingSnapshotContract
from app.repositories.ranking_snapshots_repository import RankingSnapshotsRepository


class RankingSnapshotRecorder:
    def __init__(self, repository: RankingSnapshotsRepository | None = None) -> None:
        self._repository = repository or RankingSnapshotsRepository()

    def record_many(self, conn, rankings: list[RankingSnapshotContract]) -> dict[str, int]:
        return self._repository.upsert_many(conn, rankings)
