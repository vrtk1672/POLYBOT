from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.bucket_allocation_run import (
    BucketAllocationRunCloseContract,
    BucketAllocationRunOpenContract,
)
from app.repositories.bucket_allocation_runs_repository import BucketAllocationRunsRepository


class BucketAllocationRunRecorder:
    def __init__(self, repository: BucketAllocationRunsRepository | None = None) -> None:
        self._repository = repository or BucketAllocationRunsRepository()

    def open_run(self, conn: Connection, contract: BucketAllocationRunOpenContract) -> None:
        self._repository.open_run(conn, contract)

    def close_run(self, conn: Connection, contract: BucketAllocationRunCloseContract) -> None:
        self._repository.close_run(conn, contract)
