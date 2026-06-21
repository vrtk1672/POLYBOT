from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_dashboard_truth import PaperDashboardTruthService
from app.services.source_status import SourceStatusService
from app.services.system_power import SystemPowerService


class OvernightObservationStatusService:
    """Terminal-friendly read-only overnight observation status."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def get_status(self, *, limit: int = 10) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        latest_run = _latest_run_file()
        paper = PaperDashboardTruthService(connection_factory=self._factory).get_summary(limit=limit)
        source = SourceStatusService(connection_factory=self._factory).get_dashboard_source_status()
        with self._factory.connect() as conn:
            counts = {
                "source_to_neuron_events": _count(conn, "neural_events", "metadata_json->>'source_to_neuron' = 'true'"),
                "neural_events": _count(conn, "neural_events"),
                "mesh_sessions": _count(conn, "mesh_sessions"),
                "shared_awareness": _count(conn, "mesh_shared_awareness"),
                "brain_opinions": _count(conn, "mesh_brain_opinions"),
                "coordinator_decisions": _count(conn, "mesh_coordinator_decisions"),
                "paper_intents": _count(conn, "paper_intents"),
                "paper_orders": _count(conn, "paper_orders"),
                "paper_fills": _count(conn, "paper_fills"),
                "paper_positions": _count(conn, "paper_positions"),
            }
            latest_decisions = _fetchall(
                conn,
                """
                SELECT decision_id, session_id, market_id, position_id, final_stance,
                       final_action, confidence, decision_reason, created_at
                FROM mesh_coordinator_decisions
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            )
            open_positions = _fetchall(
                conn,
                """
                SELECT id::text AS paper_position_id, market_id, intended_outcome AS side,
                       avg_entry AS entry_price, size AS quantity, opened_at, current_status
                FROM paper_positions
                WHERE closed_at IS NULL
                  AND current_status IN ('OPEN','EXIT_PENDING')
                  AND COALESCE(excluded_from_active_paper_truth, false) = false
                ORDER BY opened_at DESC
                LIMIT %s
                """,
                (limit,),
            )
        safety_status = "GREEN" if _paper_safety_green(paper) else "RED"
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK" if safety_status == "GREEN" else "RED",
                "generated_at": generated_at,
                "latest_run": latest_run,
                "event_counts": counts,
                "new_paper_trades": latest_run.get("new_paper_trades") if latest_run else None,
                "pnl": {"realized_pnl": paper.get("realized_pnl"), "unrealized_pnl": paper.get("unrealized_pnl")},
                "source_health": {
                    "status": source.get("status"),
                    "degraded_sources": source.get("degraded_sources"),
                    "missing_sources": source.get("missing_sources"),
                },
                "safety_status": safety_status,
                "safety": {
                    "live_orders": paper.get("live_orders"),
                    "real_orders_current": paper.get("real_orders_current"),
                    "orders_v2": paper.get("orders_v2"),
                    "fills_v2": paper.get("fills_v2"),
                    "canonical_positions": paper.get("canonical_positions"),
                    "paper_lineage_consistency_status": paper.get("paper_lineage_consistency_status"),
                    "capital_reconciliation_status": paper.get("capital_reconciliation_status"),
                    "mock_data": paper.get("mock_data"),
                },
                "open_positions": open_positions,
                "latest_coordinator_decisions": latest_decisions,
            }
        )


def _latest_run_file() -> dict[str, Any] | None:
    log_dir = Path("logs/overnight")
    if not log_dir.exists():
        return None
    latest = None
    for path in sorted(log_dir.glob("overnight_observation_*.log"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            last_line = ""
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        last_line = line
            payload = json.loads(last_line) if last_line else {}
            latest = {"log_path": str(path), "last_event": payload}
            if isinstance(payload, dict) and payload.get("event") == "final":
                latest.update(payload)
            return latest
        except Exception:
            continue
    return latest


def _paper_safety_green(paper: dict[str, Any]) -> bool:
    return (
        paper.get("mock_data") is False
        and int(paper.get("live_orders") or 0) == 0
        and int(paper.get("orders_v2") or 0) == int(paper.get("real_orders_current") or paper.get("real_orders_baseline") or paper.get("orders_v2") or 0)
        and str(paper.get("paper_lineage_consistency_status") or "").upper() == "OK"
        and str(paper.get("capital_reconciliation_status") or "OK").upper() != "RED"
    )


def _count(conn: Any, table: str, where: str | None = None) -> int:
    try:
        if not conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
            return 0
        sql = f"SELECT COUNT(*) AS count FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return int(conn.execute(sql).fetchone()["count"] or 0)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return 0


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value.__class__.__name__ == "Decimal":
        return float(value)
    if value.__class__.__name__ == "UUID":
        return str(value)
    return value
