from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.whale_registry_entry import WhaleRegistryEntryContract
from app.repositories.whale_registry_repository import WhaleRegistryRepository


class WhaleRegistryRecorder:
    def __init__(self, repository: WhaleRegistryRepository | None = None) -> None:
        self._repository = repository or WhaleRegistryRepository()

    def upsert(self, conn: Connection, contract: WhaleRegistryEntryContract) -> None:
        self._repository.upsert(conn, contract)
