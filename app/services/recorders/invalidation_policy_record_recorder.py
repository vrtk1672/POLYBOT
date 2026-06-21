from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.invalidation_policy_record import InvalidationPolicyRecordContract
from app.repositories.invalidation_policy_records_repository import InvalidationPolicyRecordsRepository


class InvalidationPolicyRecordRecorder:
    def __init__(self, repository: InvalidationPolicyRecordsRepository | None = None) -> None:
        self._repository = repository or InvalidationPolicyRecordsRepository()

    def record(self, conn: Connection, contract: InvalidationPolicyRecordContract) -> None:
        self._repository.insert(conn, contract)
