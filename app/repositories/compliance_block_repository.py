from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.rules_neuron.contracts import ComplianceBlock


class ComplianceBlockRepository:
    def insert_block(self, conn: Connection, block: ComplianceBlock) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO compliance_blocks (
                compliance_block_id, market_id, block_type, severity, reason,
                source, active, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (compliance_block_id) DO NOTHING
            RETURNING *
            """,
            (
                block.compliance_block_id,
                block.market_id,
                block.block_type.value,
                block.severity.value,
                block.reason,
                block.source,
                block.active,
                Jsonb(block.metadata),
            ),
        ).fetchone()

    def list_blocks(self, conn: Connection, *, active: bool | None = True, severity: str | None = None, block_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if active is not None:
            clauses.append("active = %s")
            params.append(active)
        if severity:
            clauses.append("severity = %s")
            params.append(severity)
        if block_type:
            clauses.append("block_type = %s")
            params.append(block_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(f"SELECT * FROM compliance_blocks {where} ORDER BY created_at DESC, id DESC LIMIT %s", params).fetchall()

    def list_for_market(self, conn: Connection, market_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM compliance_blocks WHERE market_id = %s AND active = true ORDER BY created_at DESC", (market_id,)).fetchall()

