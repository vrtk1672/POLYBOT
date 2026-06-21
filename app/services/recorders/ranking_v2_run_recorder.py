from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.ranking_v2_run import RankingV2RunCloseContract, RankingV2RunOpenContract
from app.repositories.ranking_v2_runs_repository import RankingV2RunsRepository


class RankingV2RunRecorder:
    def __init__(self, repository: RankingV2RunsRepository | None = None) -> None:
        self._repository = repository or RankingV2RunsRepository()

    def open_run(self, conn: Connection, contract: RankingV2RunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: RankingV2RunCloseContract) -> None:
        self._repository.close_run(conn, contract)
