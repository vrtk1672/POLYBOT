from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.invalidation_policy_run import (
    InvalidationPolicyRunCloseContract,
    InvalidationPolicyRunOpenContract,
)
from app.repositories.invalidation_policy_runs_repository import InvalidationPolicyRunsRepository


class InvalidationPolicyRunRecorder:
    def __init__(self, repository: InvalidationPolicyRunsRepository | None = None) -> None:
        self._repository = repository or InvalidationPolicyRunsRepository()

    def open_run(self, conn: Connection, contract: InvalidationPolicyRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: InvalidationPolicyRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
