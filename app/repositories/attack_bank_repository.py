from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class AttackBankRepository:
    def upsert(self, conn: Connection, *, attack_bank_id: str, values: dict[str, float], enabled: bool = True, policy: dict[str, Any] | None = None) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO attack_bank (
                attack_bank_id, available_usd, reserved_usd, used_usd, realized_profit_funded_usd,
                base_capital_used_usd, max_attack_allocation_usd, enabled, policy_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (attack_bank_id) DO UPDATE SET
                available_usd=EXCLUDED.available_usd,
                reserved_usd=EXCLUDED.reserved_usd,
                used_usd=EXCLUDED.used_usd,
                realized_profit_funded_usd=EXCLUDED.realized_profit_funded_usd,
                base_capital_used_usd=0,
                max_attack_allocation_usd=EXCLUDED.max_attack_allocation_usd,
                enabled=EXCLUDED.enabled,
                policy_json=EXCLUDED.policy_json,
                updated_at=now()
            RETURNING *
            """,
            (
                attack_bank_id,
                values.get("available_usd", 0.0),
                values.get("reserved_usd", 0.0),
                values.get("used_usd", 0.0),
                values.get("realized_profit_funded_usd", 0.0),
                0.0,
                values.get("max_attack_allocation_usd", 0.0),
                enabled,
                Jsonb(policy or {"realized_profit_only": True}),
            ),
        ).fetchone()

    def latest(self, conn: Connection) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM attack_bank ORDER BY updated_at DESC, id DESC LIMIT 1").fetchone()


