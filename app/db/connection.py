from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection, connect
from psycopg.rows import dict_row
from psycopg.sql import SQL, Identifier

from app.db.config import DatabaseSettings, get_database_settings


class DatabaseConnectionFactory:
    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self._settings = settings or get_database_settings()

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        if not self._settings.database_url:
            raise RuntimeError("POLYBOT_DATABASE_URL is not configured")
        conn = connect(self._settings.database_url, row_factory=dict_row)
        try:
            if self._settings.database_schema:
                conn.execute(
                    SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                        Identifier(self._settings.database_schema)
                    )
                )
                conn.execute(
                    SQL("SET search_path TO {}, public").format(
                        Identifier(self._settings.database_schema)
                    )
                )
                conn.commit()
            yield conn
        finally:
            conn.close()
