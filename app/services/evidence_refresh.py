from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.logging import get_logger
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.orderbook_snapshots import OrderbookSnapshotService
from app.services.signal_market_binding import SignalMarketBindingRecoveryService
from app.services.system_power import SystemPowerService

logger = get_logger(__name__)


class EvidenceRefreshService:
    """Autonomous live evidence refresh for SYSTEM ON runtime."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        orderbook_service: OrderbookSnapshotService | None = None,
        binding_service: SignalMarketBindingRecoveryService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._orderbooks = orderbook_service or OrderbookSnapshotService(connection_factory=self._factory)
        self._bindings = binding_service or SignalMarketBindingRecoveryService(connection_factory=self._factory)

    def run_refresh(self, *, cycle_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"evidence_refresh_{uuid4().hex}"
        power_state = self._system_power.get_power_state()
        system_power = str(power_state.get("power") or "OFF").upper()
        if system_power != "ON" or not bool(power_state.get("runtime_work_allowed")):
            return self._blocked_payload(run_id, cycle_id, system_power, started_at, "SYSTEM_POWER_OFF")
        if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
            return self._blocked_payload(run_id, cycle_id, system_power, started_at, "STATE_GOVERNOR_BLOCKED_INTELLIGENCE")
        existing = self._existing_for_cycle(cycle_id)
        if existing:
            payload = _json_safe(existing)
            payload["mock_data"] = False
            payload["idempotent"] = True
            return payload

        safety_before = self._safety_counts()
        blockers_before = self._blocker_counts()
        market_ids = self._relevant_market_ids(limit=limit)
        errors: list[str] = []
        orderbook: dict[str, Any] = {}
        binding: dict[str, Any] = {}
        side_result = {"sides_recovered": 0, "missing_side_count": blockers_before["missing_side"]}

        try:
            orderbook = self._orderbooks.collect_snapshots(limit=limit, market_ids=market_ids, source="brain_mesh_evidence_refresh")
        except Exception as exc:
            errors.append(f"orderbook:{type(exc).__name__}:{exc}")
            logger.exception("evidence_refresh_orderbook_failed cycle_id=%s", cycle_id)

        try:
            binding = self._bindings.recover_market_bindings(
                limit=max(limit, 50),
                apply_safe_links=True,
                create_suggestions=True,
                include_stale=False,
                include_dry_run=False,
            )
        except Exception as exc:
            errors.append(f"binding:{type(exc).__name__}:{exc}")
            logger.exception("evidence_refresh_binding_failed cycle_id=%s", cycle_id)

        try:
            side_result = self._recover_sides(limit=max(limit, 50))
        except Exception as exc:
            errors.append(f"side_recovery:{type(exc).__name__}:{exc}")
            logger.exception("evidence_refresh_side_recovery_failed cycle_id=%s", cycle_id)

        safety_after = self._safety_counts()
        blockers_after = self._blocker_counts()
        status = "DEGRADED" if errors else "OK"
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": status,
            "markets_checked": int(orderbook.get("markets_checked") or len(market_ids)),
            "orderbook_snapshots_created": int(orderbook.get("snapshots_created") or 0),
            "orderbook_failures": int(orderbook.get("error_count") or 0),
            "signals_checked": int(binding.get("signals_checked") or 0),
            "bindings_created": int(binding.get("safe_links_created") or 0),
            "bindings_refreshed": int(binding.get("already_linked") or 0),
            "bindings_rejected": int(binding.get("remained_unlinked") or 0),
            "sides_recovered": int(side_result.get("sides_recovered") or 0),
            "missing_side_count": int(side_result.get("missing_side_count") or blockers_after["missing_side"]),
            "fresh_orderbook_blockers_before": blockers_before["missing_fresh_orderbook"],
            "fresh_orderbook_blockers_after": blockers_after["missing_fresh_orderbook"],
            "binding_blockers_before": blockers_before["missing_signal_market_binding"],
            "binding_blockers_after": blockers_after["missing_signal_market_binding"],
            "missing_side_before": blockers_before["missing_side"],
            "missing_side_after": blockers_after["missing_side"],
            "orders_delta": max(0, safety_after["orders"] - safety_before["orders"]),
            "order_intents_delta": max(0, safety_after["order_intents"] - safety_before["order_intents"]),
            "fills_delta": max(0, safety_after["fills"] - safety_before["fills"]),
            "positions_delta": max(0, safety_after["positions"] - safety_before["positions"]),
            "live_actions_delta": max(0, safety_after["live_actions"] - safety_before["live_actions"]),
            "error_message": "; ".join(errors) if errors else None,
            "metadata": {
                "market_ids": market_ids,
                "orderbook_run_id": orderbook.get("run_id"),
                "binding_run_id": binding.get("run_id"),
                "ok_snapshots": orderbook.get("ok_snapshots", 0),
                "fresh_snapshots": self._fresh_orderbook_count(),
                "latest_orderbook_snapshot_at": self._latest_timestamp("orderbook_snapshots", "collected_at"),
                "latest_binding_at": self._latest_timestamp("signal_market_links", "created_at"),
                "non_executing_refresh": True,
            },
        }
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._insert_run(conn, payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        latest = self._latest_run()
        power = self._system_power.get_power_state()
        blockers = self._blocker_counts()
        return {
            "mock_data": False,
            "status": "OK" if latest else "EMPTY",
            "evidence_refresh_allowed": bool(power.get("runtime_work_allowed")),
            "evidence_refresh_active": False,
            "last_evidence_refresh_at": latest.get("finished_at") if latest else None,
            "last_evidence_refresh_status": latest.get("status") if latest else None,
            "latest_run": latest,
            "markets_checked": int(latest.get("markets_checked") or 0) if latest else 0,
            "orderbook_snapshots_created": int(latest.get("orderbook_snapshots_created") or 0) if latest else 0,
            "latest_orderbook_snapshot_at": self._latest_timestamp("orderbook_snapshots", "collected_at"),
            "orderbook_fresh_count": self._fresh_orderbook_count(),
            "orderbook_stale_count": self._stale_orderbook_count(),
            "signals_checked": int(latest.get("signals_checked") or 0) if latest else 0,
            "bindings_created": int(latest.get("bindings_created") or 0) if latest else 0,
            "bindings_refreshed": int(latest.get("bindings_refreshed") or 0) if latest else 0,
            "bindings_rejected": int(latest.get("bindings_rejected") or 0) if latest else 0,
            "latest_binding_at": self._latest_timestamp("signal_market_links", "created_at"),
            "sides_recovered": int(latest.get("sides_recovered") or 0) if latest else 0,
            "missing_side_count": blockers["missing_side"],
            "missing_fresh_orderbook_count": blockers["missing_fresh_orderbook"],
            "missing_signal_market_binding_count": blockers["missing_signal_market_binding"],
            "orders_delta": int(latest.get("orders_delta") or 0) if latest else 0,
            "order_intents_delta": int(latest.get("order_intents_delta") or 0) if latest else 0,
            "fills_delta": int(latest.get("fills_delta") or 0) if latest else 0,
            "positions_delta": int(latest.get("positions_delta") or 0) if latest else 0,
            "live_actions_delta": int(latest.get("live_actions_delta") or 0) if latest else 0,
            "paper_ready": False,
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _relevant_market_ids(self, *, limit: int) -> list[str]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = conn.execute(
                """
                WITH recent_markets AS (
                    SELECT market_id, created_at FROM coordinator_decisions WHERE market_id IS NOT NULL
                    UNION ALL
                    SELECT market_id, created_at FROM thesis_profiles WHERE market_id IS NOT NULL
                    UNION ALL
                    SELECT market_id, created_at FROM position_thesis_profiles WHERE market_id IS NOT NULL
                    UNION ALL
                    SELECT market_id, collected_at AS created_at FROM orderbook_snapshots WHERE market_id IS NOT NULL
                )
                SELECT DISTINCT rm.market_id, MAX(rm.created_at) AS latest_at
                FROM recent_markets rm
                JOIN markets_v2 m ON m.market_id = rm.market_id
                WHERE m.active = true
                  AND m.closed = false
                  AND COALESCE(m.accepting_orders, true) = true
                  AND (m.yes_token_id IS NOT NULL OR m.no_token_id IS NOT NULL)
                GROUP BY rm.market_id
                ORDER BY latest_at DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [str(row["market_id"]) for row in rows]

    def _recover_sides(self, *, limit: int) -> dict[str, int]:
        if not self._factory.enabled:
            return {"sides_recovered": 0, "missing_side_count": 0}
        with self._factory.connect() as conn, conn.transaction():
            thesis_rows = conn.execute(
                """
                WITH side_candidates AS (
                    SELECT
                        tp.thesis_id,
                        MAX(sml.link_evidence_json->>'matched_side') AS side,
                        COUNT(DISTINCT sml.link_evidence_json->>'matched_side') AS side_count
                    FROM thesis_profiles tp
                    JOIN jsonb_array_elements_text(tp.source_signal_ids) AS sig(signal_id) ON true
                    JOIN signal_market_links sml
                        ON sml.signal_id = sig.signal_id
                       AND sml.market_id = tp.market_id
                       AND sml.link_status = 'confirmed'
                       AND COALESCE(sml.is_review_required, false) = false
                       AND COALESCE(sml.link_confidence, sml.confidence, 0) >= 0.8
                    WHERE (tp.side IS NULL OR tp.side NOT IN ('YES', 'NO'))
                      AND sml.link_evidence_json->>'matched_side' IN ('YES', 'NO')
                    GROUP BY tp.thesis_id
                    HAVING COUNT(DISTINCT sml.link_evidence_json->>'matched_side') = 1
                    LIMIT %s
                )
                UPDATE thesis_profiles tp
                SET side = sc.side,
                    evidence = jsonb_set(
                        COALESCE(tp.evidence, '{}'::jsonb),
                        '{side_recovery}',
                        jsonb_build_object('source', 'signal_market_links', 'confidence', 0.8, 'recovered_at', now())
                    ),
                    updated_at = now()
                FROM side_candidates sc
                WHERE tp.thesis_id = sc.thesis_id
                RETURNING tp.thesis_id
                """,
                (limit,),
            ).fetchall()
            position_rows = conn.execute(
                """
                WITH side_candidates AS (
                    SELECT
                        pt.thesis_id,
                        MAX(sml.link_evidence_json->>'matched_side') AS side,
                        COUNT(DISTINCT sml.link_evidence_json->>'matched_side') AS side_count
                    FROM position_thesis_profiles pt
                    JOIN jsonb_array_elements_text(pt.source_signal_ids_json) AS sig(signal_id) ON true
                    JOIN signal_market_links sml
                        ON sml.signal_id = sig.signal_id
                       AND sml.market_id = pt.market_id
                       AND sml.link_status = 'confirmed'
                       AND COALESCE(sml.is_review_required, false) = false
                       AND COALESCE(sml.link_confidence, sml.confidence, 0) >= 0.8
                    WHERE (pt.side IS NULL OR pt.side NOT IN ('YES', 'NO'))
                      AND sml.link_evidence_json->>'matched_side' IN ('YES', 'NO')
                    GROUP BY pt.thesis_id
                    HAVING COUNT(DISTINCT sml.link_evidence_json->>'matched_side') = 1
                    LIMIT %s
                )
                UPDATE position_thesis_profiles pt
                SET side = sc.side,
                    metadata_json = jsonb_set(
                        COALESCE(pt.metadata_json, '{}'::jsonb),
                        '{side_recovery}',
                        jsonb_build_object('source', 'signal_market_links', 'confidence', 0.8, 'recovered_at', now())
                    ),
                    updated_at = now()
                FROM side_candidates sc
                WHERE pt.thesis_id = sc.thesis_id
                RETURNING pt.thesis_id
                """,
                (limit,),
            ).fetchall()
            missing = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM thesis_profiles WHERE side IS NULL OR side NOT IN ('YES', 'NO')) +
                    (SELECT COUNT(*) FROM position_thesis_profiles WHERE side IS NULL OR side NOT IN ('YES', 'NO')) AS count
                """
            ).fetchone()["count"]
        return {"sides_recovered": len(thesis_rows) + len(position_rows), "missing_side_count": int(missing or 0)}

    def _blocker_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {"missing_fresh_orderbook": 0, "missing_signal_market_binding": 0, "missing_side": 0, "missing_market_link": 0, "missing_mid_price": 0, "thesis_blocked": 0}
        with self._factory.connect() as conn:
            return {
                "missing_fresh_orderbook": _json_array_count(conn, "thesis_profiles", "missing_evidence", "MISSING_FRESH_ORDERBOOK") + _json_array_count(conn, "risk_decisions", "missing_requirements", "MISSING_FRESH_ORDERBOOK") + _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "MISSING_FRESH_ORDERBOOK"),
                "missing_signal_market_binding": _json_array_count(conn, "thesis_profiles", "missing_evidence", "MISSING_SIGNAL_MARKET_BINDING") + _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "MISSING_SIGNAL_MARKET_BINDING"),
                "missing_side": _count_missing_side(conn),
                "missing_market_link": _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "MISSING_MARKET_LINK"),
                "missing_mid_price": _json_array_count(conn, "exit_plans", "blockers", "MISSING_MID_PRICE") + _json_array_count(conn, "exit_plans", "missing_exit_evidence", "MISSING_MID_PRICE"),
                "thesis_blocked": _json_array_count(conn, "risk_decisions", "blockers", "THESIS_BLOCKED") + _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "THESIS_BLOCKED"),
            }

    def _fresh_orderbook_count(self) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            if not _table_exists(conn, "orderbook_snapshots"):
                return 0
            return int(conn.execute("SELECT COUNT(*) AS count FROM orderbook_snapshots WHERE is_stale = false AND snapshot_status IN ('OK','PARTIAL') AND collected_at >= now() - interval '120 seconds'").fetchone()["count"] or 0)

    def _stale_orderbook_count(self) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            if not _table_exists(conn, "orderbook_snapshots"):
                return 0
            return int(conn.execute("SELECT COUNT(*) AS count FROM orderbook_snapshots WHERE is_stale = true OR collected_at < now() - interval '120 seconds'").fetchone()["count"] or 0)

    def _latest_timestamp(self, table: str, column: str) -> str | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, table):
                return None
            row = conn.execute(f"SELECT MAX({column}) AS latest_at FROM {table}").fetchone()
            value = row["latest_at"] if row else None
            return value.isoformat() if hasattr(value, "isoformat") else value

    def _latest_run(self) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "evidence_refresh_runs"):
                return None
            row = conn.execute("SELECT * FROM evidence_refresh_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _existing_for_cycle(self, cycle_id: str | None) -> dict[str, Any] | None:
        if not cycle_id or not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "evidence_refresh_runs"):
                return None
            row = conn.execute("SELECT * FROM evidence_refresh_runs WHERE cycle_id = %s LIMIT 1", (cycle_id,)).fetchone()
            return dict(row) if row else None

    def _insert_run(self, conn: Any, payload: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO evidence_refresh_runs (
                run_id, cycle_id, system_power, started_at, finished_at, status,
                markets_checked, orderbook_snapshots_created, orderbook_failures,
                signals_checked, bindings_created, bindings_refreshed, bindings_rejected,
                sides_recovered, missing_side_count, fresh_orderbook_blockers_before,
                fresh_orderbook_blockers_after, binding_blockers_before,
                binding_blockers_after, missing_side_before, missing_side_after,
                orders_delta, order_intents_delta, fills_delta, positions_delta,
                live_actions_delta, error_message, metadata_json
            )
            VALUES (
                %(run_id)s, %(cycle_id)s, %(system_power)s, %(started_at)s, %(finished_at)s, %(status)s,
                %(markets_checked)s, %(orderbook_snapshots_created)s, %(orderbook_failures)s,
                %(signals_checked)s, %(bindings_created)s, %(bindings_refreshed)s, %(bindings_rejected)s,
                %(sides_recovered)s, %(missing_side_count)s, %(fresh_orderbook_blockers_before)s,
                %(fresh_orderbook_blockers_after)s, %(binding_blockers_before)s,
                %(binding_blockers_after)s, %(missing_side_before)s, %(missing_side_after)s,
                %(orders_delta)s, %(order_intents_delta)s, %(fills_delta)s, %(positions_delta)s,
                %(live_actions_delta)s, %(error_message)s, %(metadata_json)s
            )
            ON CONFLICT (run_id) DO NOTHING
            """,
            {**payload, "metadata_json": Jsonb(payload.get("metadata") or {})},
        )

    def _blocked_payload(self, run_id: str, cycle_id: str | None, system_power: str, started_at: datetime, reason: str) -> dict[str, Any]:
        return _json_safe({
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "BLOCKED",
            "blocked_reason": reason,
            "markets_checked": 0,
            "orderbook_snapshots_created": 0,
            "signals_checked": 0,
            "bindings_created": 0,
            "sides_recovered": 0,
            "orders_delta": 0,
            "fills_delta": 0,
            "positions_delta": 0,
            "live_actions_delta": 0,
        })

    def _safety_counts(self) -> dict[str, int]:
        return {
            "orders": _count_table(self._factory, "paper_orders") + _count_table(self._factory, "shadow_orders") + _count_table(self._factory, "live_orders") + _count_table(self._factory, "orders_v2"),
            "order_intents": _count_table(self._factory, "order_intents"),
            "fills": _count_table(self._factory, "paper_fills") + _count_table(self._factory, "fills_v2"),
            "positions": _count_table(self._factory, "positions") + _count_table(self._factory, "paper_positions") + _count_table(self._factory, "shadow_positions"),
            "live_actions": _count_table(self._factory, "live_orders"),
        }


def _json_array_count(conn: Any, table: str, column: str, value: str) -> int:
    if not _table_exists(conn, table) or not _column_exists(conn, table, column):
        return 0
    return int(conn.execute(
        f"SELECT COUNT(*) AS count FROM {table} WHERE EXISTS (SELECT 1 FROM jsonb_array_elements_text(COALESCE({column}, '[]'::jsonb)) AS item WHERE item = %s)",
        (value,),
    ).fetchone()["count"] or 0)


def _count_missing_side(conn: Any) -> int:
    total = 0
    for table in ("thesis_profiles", "position_thesis_profiles", "risk_decisions", "exit_plans", "paper_eligibility_candidates"):
        if _table_exists(conn, table) and _column_exists(conn, table, "side"):
            total += int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE side IS NULL OR side NOT IN ('YES','NO')").fetchone()["count"] or 0)
    return total


def _count_table(factory: DatabaseConnectionFactory, table: str) -> int:
    if not factory.enabled:
        return 0
    try:
        with factory.connect() as conn:
            if not _table_exists(conn, table):
                return 0
            return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
    except Exception:
        return 0


def _column_exists(conn: Any, table: str, column: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s", (table, column)).fetchone())


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value.__class__.__name__ == "Decimal":
        return float(value)
    return value
