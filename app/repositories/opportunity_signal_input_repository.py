from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.opportunity.contracts import OpportunitySignalInput


class OpportunitySignalInputRepository:
    def insert_many(self, conn: Connection, run_id: str, market_id: str, rows: list[OpportunitySignalInput]) -> None:
        for row in rows:
            conn.execute(
                """
                INSERT INTO opportunity_signal_inputs (
                    run_id, market_id, source_type, source_id, source_run_id, input_name,
                    input_value_numeric, input_value_text, input_json, weight, contribution
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    run_id, market_id, row.source_type, row.source_id, row.source_run_id,
                    row.input_name, row.input_value_numeric, row.input_value_text,
                    Jsonb(_jsonable(row.input_json)) if row.input_json is not None else None,
                    row.weight, row.contribution,
                ),
            )

    def by_run(self, conn: Connection, run_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM opportunity_signal_inputs WHERE run_id=%s ORDER BY id ASC", (run_id,)).fetchall()


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))

