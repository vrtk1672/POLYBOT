from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.bucket_allocation import BucketAllocationContract
from app.repositories.bucket_allocations_repository import BucketAllocationsRepository


class BucketAllocationRecorder:
    def __init__(self, repository: BucketAllocationsRepository | None = None) -> None:
        self._repository = repository or BucketAllocationsRepository()

    def record(self, conn: Connection, contract: BucketAllocationContract) -> None:
        self._repository.insert(conn, contract)
