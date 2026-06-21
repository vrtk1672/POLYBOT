from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.ranking_policy_run import RankingPolicyRunCloseContract, RankingPolicyRunOpenContract
from app.repositories.ranking_policy_runs_repository import RankingPolicyRunsRepository


class RankingPolicyRunRecorder:
    def __init__(self, repository: RankingPolicyRunsRepository | None = None) -> None:
        self._repository = repository or RankingPolicyRunsRepository()

    def open_run(self, conn: Connection, contract: RankingPolicyRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: RankingPolicyRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
