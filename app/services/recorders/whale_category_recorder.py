from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.whale_category import WhaleCategoryContract
from app.repositories.whale_categories_repository import WhaleCategoriesRepository


class WhaleCategoryRecorder:
    def __init__(self, repository: WhaleCategoriesRepository | None = None) -> None:
        self._repository = repository or WhaleCategoriesRepository()

    def record(self, conn: Connection, contract: WhaleCategoryContract) -> None:
        self._repository.insert(conn, contract)
