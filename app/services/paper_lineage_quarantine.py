from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.system_power import SystemPowerService


class PaperLineageQuarantineService:
    """Quarantine legacy paper rows that cannot be truthfully repaired."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)

    def run_quarantine(self, *, actor: str = "codex", limit: int = 100) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"paper_lineage_quarantine_{uuid4().hex}"
        power = self._system_power.get_power_state()
        if str(power.get("power") or power.get("system_power") or "OFF").upper() != "OFF":
            return {
                "mock_data": False,
                "run_id": run_id,
                "status": "BLOCKED_SYSTEM_NOT_OFF",
                "quarantined_count": 0,
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
            }
        if not self._factory.enabled:
            return {
                "mock_data": False,
                "run_id": run_id,
                "status": "DATABASE_UNAVAILABLE",
                "quarantined_count": 0,
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
            }

        with self._factory.connect() as conn, conn.transaction():
            rows = _legacy_inconsistent_positions(conn, limit=limit)
            quarantined: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            for row in rows:
                decision = _quarantine_decision(row)
                if decision["action"] != "QUARANTINE":
                    skipped.append(decision)
                    continue
                quarantine_id = f"paper_quarantine_{row['paper_position_id']}"
                evidence = _evidence_payload(row)
                conn.execute(
                    """
                    INSERT INTO paper_lineage_quarantine (
                        quarantine_id, run_id, entity_type, entity_id,
                        related_order_id, related_fill_id, related_intent_id,
                        reason, evidence_json, actor, metadata_json
                    )
                    VALUES (%s, %s, 'paper_position', %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (entity_type, entity_id) DO UPDATE SET
                        evidence_json = EXCLUDED.evidence_json,
                        metadata_json = EXCLUDED.metadata_json
                    """,
                    (
                        quarantine_id,
                        run_id,
                        row["paper_position_id"],
                        row.get("paper_order_id") or row.get("last_paper_order_id"),
                        row.get("paper_fill_id"),
                        row.get("source_intent_id"),
                        decision["reason"],
                        Jsonb(evidence),
                        actor,
                        Jsonb({"source": "PaperLineageQuarantineService", "decision": decision}),
                    ),
                )
                conn.execute(
                    """
                    UPDATE paper_positions
                    SET consistency_status = 'QUARANTINED',
                        current_status = 'QUARANTINED',
                        invalidated_at = COALESCE(invalidated_at, now()),
                        invalidation_reason = %s,
                        quarantine_reason = %s,
                        quarantine_source = 'PaperLineageQuarantineService',
                        quarantine_run_id = %s,
                        excluded_from_active_paper_truth = true,
                        updated_at = now(),
                        payload_json = COALESCE(payload_json, '{}'::jsonb) || %s
                    WHERE id = %s
                    """,
                    (
                        decision["reason"],
                        decision["reason"],
                        run_id,
                        Jsonb({"quarantine": {"run_id": run_id, "reason": decision["reason"], "at": datetime.now(UTC).isoformat()}}),
                        row["paper_position_id"],
                    ),
                )
                quarantined.append({"paper_position_id": row["paper_position_id"], "reason": decision["reason"]})
            _insert_dialogue(conn, run_id=run_id, actor=actor, quarantined=quarantined)

        return {
            "mock_data": False,
            "run_id": run_id,
            "status": "OK",
            "quarantined_count": len(quarantined),
            "skipped_count": len(skipped),
            "quarantined_positions": quarantined,
            "skipped": skipped,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
        }

    def audit(self, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "bad_positions": []}
        with self._factory.connect() as conn:
            rows = _legacy_inconsistent_positions(conn, limit=limit, include_quarantined=True)
            quarantined = _count_quarantined(conn)
        return {
            "mock_data": False,
            "status": "OK",
            "bad_positions": [_evidence_payload(row) for row in rows],
            "quarantined_paper_positions_count": quarantined,
        }


def _legacy_inconsistent_positions(conn: Any, *, limit: int, include_quarantined: bool = False) -> list[dict[str, Any]]:
    quarantine_filter = "" if include_quarantined else "AND COALESCE(pp.excluded_from_active_paper_truth, false) = false"
    rows = conn.execute(
        f"""
        SELECT
            pp.id::text AS paper_position_id,
            pp.market_id,
            pp.intended_outcome AS side,
            pp.current_status,
            pp.avg_entry,
            pp.size,
            pp.opened_at,
            pp.payload_json->>'source_intent_id' AS source_intent_id,
            pp.payload_json->>'paper_order_id' AS paper_order_id,
            pp.payload_json->>'last_paper_order_id' AS last_paper_order_id,
            pp.payload_json->>'paper_fill_id' AS paper_fill_id,
            COALESCE(pp.excluded_from_active_paper_truth, false) AS excluded_from_active_paper_truth,
            pp.consistency_status,
            EXISTS(SELECT 1 FROM paper_orders po WHERE po.id::text = COALESCE(pp.payload_json->>'paper_order_id', pp.payload_json->>'last_paper_order_id')) AS matching_order_exists,
            EXISTS(SELECT 1 FROM paper_fills pf WHERE pf.paper_fill_id = pp.payload_json->>'paper_fill_id') AS matching_fill_exists,
            EXISTS(SELECT 1 FROM paper_intents pi WHERE pi.paper_intent_id = pp.payload_json->>'source_intent_id') AS matching_intent_exists,
            EXISTS(SELECT 1 FROM paper_trade_ledger ptl WHERE ptl.position_id=pp.id AND ptl.event_type='OPEN') AS open_ledger_exists,
            EXISTS(SELECT 1 FROM paper_trade_ledger ptl WHERE ptl.position_id=pp.id AND ptl.event_type='CLOSE') AS close_ledger_exists,
            EXISTS(SELECT 1 FROM paper_position_closes ppc WHERE ppc.position_id=pp.id) AS close_exists,
            pr.mode AS source_mode,
            ps.payload_json->>'stage' AS signal_stage,
            pp.payload_json
        FROM paper_positions pp
        LEFT JOIN paper_runs pr ON pr.id=pp.paper_run_id
        LEFT JOIN paper_orders po ON po.id::text = COALESCE(pp.payload_json->>'paper_order_id', pp.payload_json->>'last_paper_order_id')
        LEFT JOIN paper_signals ps ON ps.id=po.paper_signal_id
        WHERE (
            pp.payload_json->>'paper_fill_id' IS NULL
            OR NOT EXISTS (SELECT 1 FROM paper_fills pf WHERE pf.paper_fill_id = pp.payload_json->>'paper_fill_id')
            OR NOT EXISTS (SELECT 1 FROM paper_trade_ledger ptl WHERE ptl.position_id=pp.id AND ptl.event_type='OPEN')
        )
        {quarantine_filter}
        ORDER BY pp.opened_at ASC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _quarantine_decision(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("matching_fill_exists") and row.get("open_ledger_exists") and row.get("matching_intent_exists"):
        return {"action": "REPAIR_NOT_NEEDED", "reason": "LINEAGE_COMPLETE"}
    if row.get("matching_fill_exists") or row.get("open_ledger_exists"):
        return {"action": "SKIP_MANUAL_REVIEW", "reason": "PARTIAL_REAL_EVIDENCE_PRESENT"}
    return {
        "action": "QUARANTINE",
        "reason": "LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER",
    }


def _evidence_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "paper_position_id": row.get("paper_position_id"),
        "market_id": row.get("market_id"),
        "side": row.get("side"),
        "status": row.get("current_status"),
        "entry_price": _json_safe(row.get("avg_entry")),
        "quantity": _json_safe(row.get("size")),
        "opened_at": row.get("opened_at").isoformat() if hasattr(row.get("opened_at"), "isoformat") else row.get("opened_at"),
        "source_intent_id": row.get("source_intent_id"),
        "paper_order_id": row.get("paper_order_id") or row.get("last_paper_order_id"),
        "paper_fill_id": row.get("paper_fill_id"),
        "matching_paper_order_exists": bool(row.get("matching_order_exists")),
        "matching_paper_fill_exists": bool(row.get("matching_fill_exists")),
        "matching_paper_intent_exists": bool(row.get("matching_intent_exists")),
        "open_ledger_row_exists": bool(row.get("open_ledger_exists")),
        "close_ledger_row_exists": bool(row.get("close_ledger_exists")),
        "close_row_exists": bool(row.get("close_exists")),
        "source_service": row.get("source_mode") or row.get("signal_stage"),
        "why_invalid": "missing paper_fill_id and OPEN paper_trade_ledger row",
        "recommended_action": "QUARANTINE",
        "reason_for_action": "no true fill or ledger evidence exists to repair without fabrication",
        "excluded_from_active_paper_truth": bool(row.get("excluded_from_active_paper_truth")),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _insert_dialogue(conn: Any, *, run_id: str, actor: str, quarantined: list[dict[str, Any]]) -> None:
    if not quarantined or not _table_exists(conn, "brain_dialogue_events"):
        return
    count = len(quarantined)
    message = (
        f"Paper Lineage Quarantine: I quarantined {count} legacy paper positions because they had no "
        "paper_fill_id and no OPEN ledger row. They are excluded from active Paper truth but preserved for audit."
    )
    conn.execute(
        """
        INSERT INTO brain_dialogue_events (
            dialogue_id, source_table, source_record_id, timestamp, component,
            component_type, event_type, severity, status, what_i_saw,
            what_i_understand, decision, human_message, raw_payload_json
        )
        VALUES (%s, 'paper_lineage_quarantine', %s, now(), 'Paper Lineage Quarantine',
                'paper', 'PAPER_LINEAGE_QUARANTINE', 'WARN', 'QUARANTINED',
                %s, %s, 'QUARANTINE_LEGACY_ROWS', %s, %s)
        ON CONFLICT (source_table, source_record_id, event_type) DO NOTHING
        """,
        (
            f"brain_dialogue_{uuid4().hex}",
            run_id,
            f"Found {count} legacy paper positions without fill/ledger lineage.",
            "Rows cannot be truthfully repaired without creating fake fills or fake PnL.",
            message,
            Jsonb({"actor": actor, "quarantined_positions": quarantined}),
        ),
    )


def _count_quarantined(conn: Any) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM paper_positions WHERE COALESCE(excluded_from_active_paper_truth, false) = true"
    ).fetchone()
    return int(row["count"] or 0)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])
