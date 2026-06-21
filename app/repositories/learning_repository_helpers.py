from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from psycopg import Connection


def row_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    output: dict[str, Any] = {}
    for key, value in dict(row).items():
        if isinstance(value, Decimal):
            output[key] = float(value)
        elif isinstance(value, datetime):
            output[key] = value.isoformat()
        else:
            output[key] = value
    return output


def rows(rows_: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row_dict(row) or {} for row in rows_]


def recent(conn: Connection, table: str, limit: int = 100) -> list[dict[str, Any]]:
    return rows(conn.execute(f"SELECT * FROM {table} ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall())


def count_today(conn: Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE created_at::date=CURRENT_DATE").fetchone()["count"] or 0)

