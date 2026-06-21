from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.brains.contracts import CapitalBrainOutput


class CapitalBrainOutputRepository:
    def insert(self, conn: Connection, run_id: str, market_family: str | None, candidate_engine: str | None, output: CapitalBrainOutput) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO capital_brain_outputs (
                run_id, market_id, market_family, candidate_engine, capital_allowed, block_reason,
                max_position_size_usd, max_position_size_contracts, risk_budget_usd, capital_bucket,
                cash_reserve_after_usd, available_capital_usd, locked_capital_usd, open_exposure_usd,
                engine_budget_remaining_usd, capital_recycling_score, allocation_confidence,
                allocation_reason, constraints_json, insufficient_data, insufficient_data_reasons_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                run_id, output.market_id, market_family, candidate_engine, output.capital_allowed, output.block_reason,
                output.max_position_size_usd, output.max_position_size_contracts, output.risk_budget_usd,
                output.capital_bucket, output.cash_reserve_after_usd, output.available_capital_usd,
                output.locked_capital_usd, output.open_exposure_usd, output.engine_budget_remaining_usd,
                output.capital_recycling_score, output.allocation_confidence, output.allocation_reason,
                Jsonb(output.constraints), output.insufficient_data, Jsonb(output.insufficient_data_reasons),
            ),
        ).fetchone()

    def latest_for_market(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM capital_brain_outputs WHERE market_id=%s ORDER BY created_at DESC, id DESC LIMIT 1", (market_id,)).fetchone()

    def recent(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM capital_brain_outputs ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

    def blocked(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM capital_brain_outputs WHERE capital_allowed IS FALSE OR insufficient_data IS TRUE ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()
