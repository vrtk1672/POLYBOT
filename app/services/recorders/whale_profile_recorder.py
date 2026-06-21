from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.whale_profile import WhaleProfileContract
from app.repositories.whale_profiles_repository import WhaleProfilesRepository


class WhaleProfileRecorder:
    def __init__(self, repository: WhaleProfilesRepository | None = None) -> None:
        self._repository = repository or WhaleProfilesRepository()

    def record(self, conn: Connection, contract: WhaleProfileContract) -> None:
        self._repository.insert(conn, contract)
