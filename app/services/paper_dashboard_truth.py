from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.control_center.truth_hardening import classify_freshness, readiness_from_blockers, truth_from_freshness
from app.control_center.truth_contract import ControlCenterFreshnessState, ControlCenterRuntimeState
from app.db.connection import DatabaseConnectionFactory
from app.services.paper_capital import PaperCapitalService
from app.services.system_power import SystemPowerService
from app.stage4 import get_stage4_settings

PAPER_INTENT_FRESH_AFTER_SECONDS = 600
ORDERBOOK_FRESH_AFTER_SECONDS = 180
RUNTIME_CYCLE_FRESH_AFTER_SECONDS = 300


class PaperDashboardTruthService:
    """Read-only paper dashboard, regression, and soak-readiness truth."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)

    def get_summary(self, *, limit: int = 50) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return self._unavailable("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn:
            counts = self._counts(conn)
            timestamps = self._timestamps(conn)
            pnl = self._pnl(conn)
            safety = self._safety(conn)
            latest = self._latest_runtime(conn)
            integrity = self._integrity(conn)
            dialogue = self._dialogue(conn)
            capital = PaperCapitalService(connection_factory=self._factory, system_power=self._system_power).get_dashboard_summary(limit=10)
            blockers = self._blockers(conn, limit=limit)
            power = self._power_state()
            stage4 = get_stage4_settings()
            live_enabled = bool(stage4.live_trading_enabled)
            shadow_enabled = False
            warnings = self._warnings(power, safety, integrity, pnl, latest, live_enabled, shadow_enabled)
            if capital.get("capital_reconciliation_status") == "RED":
                warnings = [*warnings, "PAPER_CAPITAL_RECONCILIATION_RED"]
            ledger_health_status = self._readiness_status(warnings)
            current_truth = self._current_paper_truth(conn, power=power, counts=counts, timestamps=timestamps, latest=latest)
            status = current_truth["readiness_state"]
            combined_warnings = _unique_strings([*warnings, *current_truth["warnings"]])
            return _json_safe(
                {
                    "mock_data": False,
                    "source": "paper_* tables + system_power + runtime_cycles_v2 + orderbook_snapshots",
                    "generated_at": generated_at,
                    "last_updated": current_truth["last_updated"],
                    "age_seconds": current_truth["age_seconds"],
                    "freshness_state": current_truth["freshness_state"],
                    "runtime_state": current_truth["runtime_state"],
                    "truth_state": current_truth["truth_state"],
                    "readiness_state": current_truth["readiness_state"],
                    "system_power": power.get("system_power") or power.get("power"),
                    "runtime_health": latest.get("runtime_health"),
                    "paper_status": status,
                    "paper_ledger_health_status": ledger_health_status,
                    "paper_execution_readiness_state": current_truth["readiness_state"],
                    "paper_execution_blockers": current_truth["blockers"],
                    "paper_execution_explanation": current_truth["explanation"],
                    "market_data_readiness": current_truth["market_data_readiness"],
                    "orderbook_readiness": current_truth["orderbook_readiness"],
                    "paper_intents_total": counts["paper_intents"],
                    "executable_paper_intents": counts["executable_paper_intents"],
                    "paper_orders_total": counts["paper_orders"],
                    "paper_fills_total": counts["paper_fills"],
                    "paper_positions_total": counts["paper_positions"],
                    "open_paper_positions": counts["open_paper_positions"],
                    "active_open_paper_positions": counts["open_paper_positions"],
                    "raw_open_paper_positions": counts["raw_open_paper_positions"],
                    "closed_paper_positions": counts["closed_paper_positions"],
                    "quarantined_paper_positions_count": integrity["quarantined_paper_positions_count"],
                    "quarantined_paper_positions": integrity["quarantined_paper_positions"],
                    "paper_position_closes": counts["paper_position_closes"],
                    "paper_trade_ledger": counts["paper_trade_ledger"],
                    "paper_daily_pnl": counts["paper_daily_pnl"],
                    "latest_paper_intent_at": timestamps["latest_paper_intent_at"],
                    "latest_paper_order_at": timestamps["latest_paper_order_at"],
                    "latest_paper_fill_at": timestamps["latest_paper_fill_at"],
                    "latest_paper_position_at": timestamps["latest_paper_position_at"],
                    "latest_exit_check_at": timestamps["latest_exit_check_at"],
                    "latest_position_close_at": timestamps["latest_position_close_at"],
                    "realized_pnl": pnl["realized_pnl"],
                    "unrealized_pnl": pnl["unrealized_pnl"],
                    "daily_pnl": pnl["daily_pnl"],
                    "gross_profit": pnl["gross_profit"],
                    "gross_loss": pnl["gross_loss"],
                    "winning_trades_count": pnl["winning_trades_count"],
                    "losing_trades_count": pnl["losing_trades_count"],
                    "orphan_positions_count": integrity["orphan_positions_count"],
                    "duplicate_orders_count": integrity["duplicate_orders_count"],
                    "duplicate_fills_count": integrity["duplicate_fills_count"],
                    "duplicate_positions_count": integrity["duplicate_positions_count"],
                    "duplicate_intent_orders_count": integrity["duplicate_intent_orders_count"],
                    "duplicate_order_fills_count": integrity["duplicate_order_fills_count"],
                    "duplicate_fill_positions_count": integrity["duplicate_fill_positions_count"],
                    "positions_without_fills_count": integrity["positions_without_fills_count"],
                    "raw_positions_without_fills_count": integrity["raw_positions_without_fills_count"],
                    "fills_without_orders_count": integrity["fills_without_orders_count"],
                    "positions_without_open_ledger_count": integrity["positions_without_open_ledger_count"],
                    "raw_positions_without_open_ledger_count": integrity["raw_positions_without_open_ledger_count"],
                    "closed_positions_without_close_count": integrity["closed_positions_without_close_count"],
                    "closed_positions_without_close_ledger_count": integrity["closed_positions_without_close_ledger_count"],
                    "executed_intents_reexecuted_count": integrity["executed_intents_reexecuted_count"],
                    "paper_lineage_consistency_status": integrity["paper_lineage_consistency_status"],
                    "paper_lineage_consistency_raw_status": integrity["paper_lineage_consistency_raw_status"],
                    "paper_lineage_readiness_status": integrity["paper_lineage_readiness_status"],
                    "stale_price_count": integrity["stale_price_count"],
                    "no_fake_pnl": pnl["no_fake_pnl"],
                    "live_orders": safety["live_orders"],
                    "real_orders_baseline": safety["real_orders"],
                    "real_orders_current": safety["real_orders"],
                    "orders_v2": safety["orders_v2"],
                    "fills_v2": safety["fills_v2"],
                    "canonical_positions": safety["canonical_positions"],
                    "live_enabled": live_enabled,
                    "shadow_enabled": shadow_enabled,
                    "brain_dialogue_latest_at": dialogue["brain_dialogue_latest_at"],
                    "neuron_dialogue_latest_at": dialogue["neuron_dialogue_latest_at"],
                    "brain_dialogue_events": dialogue["brain_dialogue_events"],
                    "neuron_dialogue_events": dialogue["neuron_dialogue_events"],
                    "top_current_blockers": blockers,
                    "capital_summary": capital,
                    "capital_reconciliation_status": capital.get("capital_reconciliation_status"),
                    "capital_status": capital.get("capital_status"),
                    "available_balance": capital.get("available_balance"),
                    "locked_balance": capital.get("locked_balance"),
                    "open_exposure": capital.get("open_exposure"),
                    "expected_locked_balance": capital.get("expected_locked_balance"),
                    "actual_locked_balance": capital.get("actual_locked_balance"),
                    "expected_open_exposure": capital.get("expected_open_exposure"),
                    "actual_open_exposure": capital.get("actual_open_exposure"),
                    "open_positions_without_lock": capital.get("open_positions_without_lock"),
                    "locks_without_open_position": capital.get("locks_without_open_position"),
                    "closed_positions_with_active_lock": capital.get("closed_positions_with_active_lock"),
                    "closes_without_release": capital.get("closes_without_release"),
                    "closes_without_realized_pnl_applied": capital.get("closes_without_realized_pnl_applied"),
                    "duplicate_releases": capital.get("duplicate_releases"),
                    "realized_pnl_double_apply_count": capital.get("realized_pnl_double_apply_count"),
                    "duplicate_realized_pnl_apply_count": capital.get("duplicate_realized_pnl_apply_count"),
                    "active_capital_guards": capital.get("active_guards"),
                    "warnings": combined_warnings,
                    "readiness_status": status,
                    "latest_runtime": latest,
                }
            )

    def get_positions(self, *, limit: int = 100) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return {"mock_data": False, "generated_at": generated_at, "positions": [], "count": 0, "status": "DATABASE_UNAVAILABLE"}
        with self._factory.connect() as conn:
            rows = _fetchall(
                conn,
                """
                SELECT *
                FROM paper_positions
                ORDER BY opened_at DESC NULLS LAST, updated_at DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )
        positions = [self._position_payload(row) for row in rows]
        return _json_safe({"mock_data": False, "generated_at": generated_at, "count": len(positions), "positions": positions})

    def get_pnl(self, *, limit: int = 30) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return {"mock_data": False, "generated_at": generated_at, "status": "DATABASE_UNAVAILABLE"}
        with self._factory.connect() as conn:
            pnl = self._pnl(conn)
            integrity = self._integrity(conn)
            rows = _fetchall(
                conn,
                "SELECT * FROM paper_daily_pnl ORDER BY pnl_date DESC LIMIT %s",
                (limit,),
            )
            status = "OK" if integrity["paper_lineage_consistency_status"] == "OK" and pnl["no_fake_pnl"] else "RED"
            return _json_safe(
                {
                    "mock_data": False,
                    "generated_at": generated_at,
                    "paper_daily_pnl": rows,
                    "realized_pnl": pnl["realized_pnl"],
                    "unrealized_pnl": pnl["unrealized_pnl"],
                    "net_pnl": pnl["net_pnl"],
                    "gross_profit": pnl["gross_profit"],
                    "gross_loss": pnl["gross_loss"],
                    "closed_trades": pnl["closed_trades_count"],
                    "open_positions": _count_open_positions(conn),
                    "pnl_source": pnl["pnl_source"],
                    "stale_price_count": integrity["stale_price_count"],
                    "paper_lineage_consistency_status": integrity["paper_lineage_consistency_status"],
                    "paper_lineage_readiness_status": integrity["paper_lineage_readiness_status"],
                    "quarantined_paper_positions_count": integrity["quarantined_paper_positions_count"],
                    "reconciliation_status": status,
                }
            )

    def get_soak_readiness(self) -> dict[str, Any]:
        summary = self.get_summary()
        blockers = list(summary.get("paper_execution_blockers") or summary.get("warnings") or [])
        audit_warnings: list[str] = []
        if _int(summary.get("quarantined_paper_positions_count")) > 0:
            audit_warnings.append("QUARANTINED_LEGACY_PAPER_POSITIONS_PRESENT")
        endpoint_status = {
            "/healthz": "CHECK_EXTERNALLY",
            "/runtime/health": "CHECK_EXTERNALLY",
            "/system/power": "CHECK_EXTERNALLY",
            "/dashboard/api/v2/paper": "OK",
            "/dashboard/api/v2/paper/positions": "OK",
            "/dashboard/api/v2/paper/pnl": "OK",
            "/dashboard/api/v2/brain-dialogue": "CHECK_EXTERNALLY",
            "/dashboard/api/v2/neuron-dialogue": "CHECK_EXTERNALLY",
        }
        safety_ok = (
            summary.get("live_orders") == 0
            and not summary.get("live_enabled")
            and not summary.get("shadow_enabled")
            and summary.get("orphan_positions_count") == 0
            and summary.get("duplicate_fills_count") == 0
            and summary.get("duplicate_positions_count") == 0
            and summary.get("paper_lineage_consistency_status") == "OK"
            and summary.get("no_fake_pnl") is True
        )
        readiness = summary.get("readiness_state") or ("READY" if safety_ok and not blockers else ("NOT_READY" if not safety_ok else "PARTIAL"))
        return _json_safe(
            {
                "mock_data": False,
                "generated_at": datetime.now(UTC).isoformat(),
                "readiness_status": readiness,
                "blockers": blockers if readiness != "GREEN" else [],
                "warnings": blockers if readiness == "YELLOW" else audit_warnings,
                "safety_status": "GREEN" if safety_ok else "RED",
                "preflight_counts": {
                    key: summary.get(key)
                    for key in (
                        "paper_intents_total",
                        "executable_paper_intents",
                        "paper_orders_total",
                        "paper_fills_total",
                        "paper_positions_total",
                        "open_paper_positions",
                        "active_open_paper_positions",
                        "raw_open_paper_positions",
                        "closed_paper_positions",
                        "paper_position_closes",
                        "paper_trade_ledger",
                        "paper_daily_pnl",
                        "duplicate_intent_orders_count",
                        "duplicate_order_fills_count",
                        "duplicate_fill_positions_count",
                        "positions_without_fills_count",
                        "raw_positions_without_fills_count",
                        "positions_without_open_ledger_count",
                        "raw_positions_without_open_ledger_count",
                        "executed_intents_reexecuted_count",
                        "paper_lineage_consistency_status",
                        "paper_lineage_readiness_status",
                        "quarantined_paper_positions_count",
                        "brain_dialogue_events",
                        "neuron_dialogue_events",
                        "live_orders",
                        "real_orders_current",
                        "orders_v2",
                        "fills_v2",
                        "canonical_positions",
                    )
                },
                "required_endpoints_status": endpoint_status,
                "can_start_4h_soak": readiness == "READY",
            }
        )

    def _counts(self, conn: Any) -> dict[str, int]:
        return {
            "paper_intents": _count(conn, "paper_intents"),
            "executable_paper_intents": _count_executable_intents(conn),
            "paper_orders": _count(conn, "paper_orders"),
            "paper_fills": _count(conn, "paper_fills"),
            "paper_positions": _count(conn, "paper_positions"),
            "open_paper_positions": _count_open_positions(conn),
            "raw_open_paper_positions": _count_where(conn, "paper_positions", "closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING')"),
            "closed_paper_positions": _count_where(conn, "paper_positions", "current_status = 'CLOSED' OR closed_at IS NOT NULL"),
            "paper_position_closes": _count(conn, "paper_position_closes"),
            "paper_trade_ledger": _count(conn, "paper_trade_ledger"),
            "paper_daily_pnl": _count(conn, "paper_daily_pnl"),
        }

    def _timestamps(self, conn: Any) -> dict[str, Any]:
        return {
            "latest_paper_intent_at": _max_ts(conn, "paper_intents", "created_at"),
            "latest_paper_order_at": _max_ts(conn, "paper_orders", "created_at"),
            "latest_paper_fill_at": _max_ts(conn, "paper_fills", "created_at"),
            "latest_paper_position_at": _max_ts(conn, "paper_positions", "opened_at"),
            "latest_exit_check_at": _max_ts(conn, "paper_exit_loop_runs", "created_at"),
            "latest_position_close_at": _max_ts(conn, "paper_position_closes", "created_at"),
        }

    def _pnl(self, conn: Any) -> dict[str, Any]:
        daily = _fetchone(conn, "SELECT * FROM paper_daily_pnl ORDER BY pnl_date DESC LIMIT 1")
        close_row = _fetchone(
            conn,
            """
            SELECT
                COALESCE(SUM(realized_pnl), 0) AS realized_pnl,
                COALESCE(SUM(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS gross_profit,
                COALESCE(SUM(realized_pnl) FILTER (WHERE realized_pnl < 0), 0) AS gross_loss,
                COUNT(*) AS closed_trades_count,
                COUNT(*) FILTER (WHERE realized_pnl > 0) AS winning_trades_count,
                COUNT(*) FILTER (WHERE realized_pnl < 0) AS losing_trades_count
            FROM paper_position_closes
            """,
        )
        open_row = _fetchone(
            conn,
            """
            SELECT COALESCE(SUM(unrealized), 0) AS unrealized_pnl
            FROM paper_positions
            WHERE closed_at IS NULL AND current_status IN ('OPEN', 'EXIT_PENDING')
              AND COALESCE(excluded_from_active_paper_truth, false) = false
            """,
        )
        realized = _decimal((daily or {}).get("realized_pnl"), (close_row or {}).get("realized_pnl"))
        unrealized = _decimal((daily or {}).get("unrealized_pnl"), (open_row or {}).get("unrealized_pnl"))
        closed_count = _int((daily or {}).get("closed_trades_count"), (close_row or {}).get("closed_trades_count"))
        no_fake_pnl = not (realized != 0 and closed_count == 0)
        return {
            "daily_pnl": daily,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "net_pnl": realized + unrealized,
            "gross_profit": _decimal((daily or {}).get("gross_profit"), (close_row or {}).get("gross_profit")),
            "gross_loss": _decimal((daily or {}).get("gross_loss"), (close_row or {}).get("gross_loss")),
            "winning_trades_count": _int((daily or {}).get("winning_trades_count"), (close_row or {}).get("winning_trades_count")),
            "losing_trades_count": _int((daily or {}).get("losing_trades_count"), (close_row or {}).get("losing_trades_count")),
            "closed_trades_count": closed_count,
            "pnl_source": "paper_daily_pnl" if daily else "paper_position_closes+paper_positions",
            "no_fake_pnl": no_fake_pnl,
        }

    def _safety(self, conn: Any) -> dict[str, int]:
        real_orders = _count(conn, "orders_v2")
        return {
            "live_orders": _count(conn, "live_orders"),
            "real_orders": real_orders,
            "orders_v2": real_orders,
            "fills_v2": _count(conn, "fills_v2"),
            "canonical_positions": _count(conn, "positions"),
        }

    def _integrity(self, conn: Any) -> dict[str, int]:
        integrity = {
            "orphan_positions_count": _orphan_positions(conn),
            "duplicate_orders_count": _duplicate_payload_source(conn, "paper_orders", "payload_json", "source_intent_id"),
            "duplicate_fills_count": _duplicate_column(conn, "paper_fills", "source_intent_id"),
            "duplicate_positions_count": _duplicate_payload_source(conn, "paper_positions", "payload_json", "source_intent_id"),
            "duplicate_intent_orders_count": _duplicate_payload_source(conn, "paper_orders", "payload_json", "source_intent_id"),
            "duplicate_order_fills_count": _duplicate_column(conn, "paper_fills", "paper_order_id"),
            "duplicate_fill_positions_count": _duplicate_payload_source(conn, "paper_positions", "payload_json", "paper_fill_id"),
            "positions_without_fills_count": _positions_without_fills(conn),
            "raw_positions_without_fills_count": _positions_without_fills(conn, include_quarantined=True),
            "fills_without_orders_count": _fills_without_orders(conn),
            "positions_without_open_ledger_count": _positions_without_open_ledger(conn),
            "raw_positions_without_open_ledger_count": _positions_without_open_ledger(conn, include_quarantined=True),
            "closed_positions_without_close_count": _closed_positions_without_close(conn),
            "closed_positions_without_close_ledger_count": _closed_positions_without_close_ledger(conn),
            "executed_intents_reexecuted_count": _executed_intents_reexecuted(conn),
            "stale_price_count": _count_where(conn, "paper_positions", "closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING') AND mark_price IS NULL"),
            "quarantined_paper_positions_count": _quarantined_positions_count(conn),
            "quarantined_paper_positions": _quarantined_positions(conn, limit=10),
        }
        critical = {
            "orphan_positions_count",
            "duplicate_intent_orders_count",
            "duplicate_order_fills_count",
            "duplicate_fill_positions_count",
            "positions_without_fills_count",
            "fills_without_orders_count",
            "positions_without_open_ledger_count",
            "closed_positions_without_close_count",
            "closed_positions_without_close_ledger_count",
            "executed_intents_reexecuted_count",
        }
        active_red = any(integrity[key] > 0 for key in critical)
        raw_red = (
            active_red
            or integrity["raw_positions_without_fills_count"] > 0
            or integrity["raw_positions_without_open_ledger_count"] > 0
        )
        integrity["paper_lineage_readiness_status"] = "RED" if active_red else "OK"
        integrity["paper_lineage_consistency_status"] = "RED" if active_red else "OK"
        integrity["paper_lineage_consistency_raw_status"] = "RED" if raw_red else "OK"
        return integrity

    def _latest_runtime(self, conn: Any) -> dict[str, Any]:
        cycle = _fetchone(conn, "SELECT * FROM runtime_cycles_v2 ORDER BY started_at DESC NULLS LAST, id DESC LIMIT 1")
        service = _fetchone(conn, "SELECT * FROM service_health WHERE service_name = 'scheduler' ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 1")
        last_success = _fetchone(
            conn,
            """
            SELECT *
            FROM runtime_cycles_v2
            WHERE status = 'COMPLETED'
            ORDER BY finished_at DESC NULLS LAST, started_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
        )
        active_cycle = _fetchone(
            conn,
            """
            SELECT *
            FROM runtime_cycles_v2
            WHERE status = 'RUNNING'
            ORDER BY started_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
        )
        return {
            "runtime_health": "OK" if cycle else "NO_RUNTIME_CYCLE",
            "scheduler_health": (service or {}).get("status"),
            "latest_cycle_id": (cycle or {}).get("cycle_id"),
            "latest_cycle_at": (cycle or {}).get("started_at") or (cycle or {}).get("created_at"),
            "last_successful_cycle_id": (last_success or {}).get("cycle_id"),
            "last_successful_cycle_at": (last_success or {}).get("finished_at") or (last_success or {}).get("started_at"),
            "active_cycle_id": (active_cycle or {}).get("cycle_id"),
            "active_cycle_at": (active_cycle or {}).get("started_at"),
        }

    def _current_paper_truth(
        self,
        conn: Any,
        *,
        power: dict[str, Any],
        counts: dict[str, int],
        timestamps: dict[str, Any],
        latest: dict[str, Any],
    ) -> dict[str, Any]:
        blockers: list[str] = []
        warnings: list[str] = []
        system_power = power.get("system_power") or power.get("power")
        if system_power != "ON":
            blockers.append("SYSTEM_POWER_OFF")

        latest_intent_at = timestamps.get("latest_paper_intent_at")
        latest_orderbook_at = _max_ts(conn, "orderbook_snapshots", "snapshot_at") or _max_ts(conn, "orderbook_snapshots", "collected_at")
        latest_cycle_at = latest.get("last_successful_cycle_at") or latest.get("latest_cycle_at")

        intent_freshness, intent_age = classify_freshness(latest_intent_at, stale_after_seconds=PAPER_INTENT_FRESH_AFTER_SECONDS)
        orderbook_freshness, orderbook_age = classify_freshness(latest_orderbook_at, stale_after_seconds=ORDERBOOK_FRESH_AFTER_SECONDS)
        runtime_freshness, runtime_age = classify_freshness(latest_cycle_at, stale_after_seconds=RUNTIME_CYCLE_FRESH_AFTER_SECONDS)

        if intent_freshness == ControlCenterFreshnessState.MISSING:
            blockers.append("MISSING_PAPER_INTENT_SOURCE")
        elif intent_freshness == ControlCenterFreshnessState.STALE:
            blockers.append("STALE_PAPER_INTENT_SOURCE")
        if orderbook_freshness == ControlCenterFreshnessState.MISSING:
            blockers.append("MISSING_ORDERBOOK_SOURCE")
        elif orderbook_freshness == ControlCenterFreshnessState.STALE:
            blockers.append("STALE_ORDERBOOK_SOURCE")
        if runtime_freshness == ControlCenterFreshnessState.MISSING:
            blockers.append("MISSING_RUNTIME_CYCLE_SOURCE")
        elif runtime_freshness == ControlCenterFreshnessState.STALE:
            blockers.append("STALE_RUNTIME_CYCLE_SOURCE")
        if counts["executable_paper_intents"] <= 0:
            blockers.append("NO_CURRENT_EXECUTABLE_PAPER_INTENTS")

        active_cycle_at = latest.get("active_cycle_at")
        active_freshness, active_age = classify_freshness(active_cycle_at, stale_after_seconds=RUNTIME_CYCLE_FRESH_AFTER_SECONDS)
        if latest.get("active_cycle_id") and active_freshness == ControlCenterFreshnessState.STALE:
            warnings.append("ACTIVE_RUNTIME_CYCLE_ROW_IS_STALE")

        freshest = _latest_of([latest_intent_at, latest_orderbook_at])
        combined_freshness, age = classify_freshness(freshest, stale_after_seconds=ORDERBOOK_FRESH_AFTER_SECONDS)
        readiness_state = readiness_from_blockers(blockers).value
        runtime_state = ControlCenterRuntimeState.RUNNING.value
        if system_power != "ON":
            runtime_state = ControlCenterRuntimeState.STOPPED.value
        elif runtime_freshness == ControlCenterFreshnessState.STALE:
            runtime_state = ControlCenterRuntimeState.STALE.value
        elif blockers:
            runtime_state = ControlCenterRuntimeState.BLOCKED.value

        return {
            "last_updated": freshest,
            "age_seconds": age,
            "freshness_state": combined_freshness.value,
            "truth_state": truth_from_freshness(combined_freshness, has_history=bool(freshest)).value,
            "runtime_state": runtime_state,
            "readiness_state": readiness_state,
            "blockers": _unique_strings(blockers),
            "warnings": _unique_strings(warnings),
            "explanation": {
                "current_truth_wins": True,
                "historical_success_does_not_imply_readiness": True,
                "system_power": system_power,
                "latest_paper_intent_at": latest_intent_at,
                "latest_paper_intent_age_seconds": intent_age,
                "latest_orderbook_at": latest_orderbook_at,
                "latest_orderbook_age_seconds": orderbook_age,
                "last_successful_cycle_at": latest.get("last_successful_cycle_at"),
                "last_successful_cycle_age_seconds": runtime_age,
                "active_cycle_id": latest.get("active_cycle_id"),
                "active_cycle_at": active_cycle_at,
                "active_cycle_age_seconds": active_age,
                "executable_paper_intents": counts["executable_paper_intents"],
            },
            "market_data_readiness": {
                "source": "runtime_cycles_v2",
                "freshness_state": runtime_freshness.value,
                "readiness_state": "READY" if runtime_freshness == ControlCenterFreshnessState.FRESH else "NOT_READY",
                "last_updated": latest_cycle_at,
                "age_seconds": runtime_age,
            },
            "orderbook_readiness": {
                "source": "orderbook_snapshots",
                "freshness_state": orderbook_freshness.value,
                "readiness_state": "READY" if orderbook_freshness == ControlCenterFreshnessState.FRESH else "NOT_READY",
                "last_updated": latest_orderbook_at,
                "age_seconds": orderbook_age,
            },
        }

    def _dialogue(self, conn: Any) -> dict[str, Any]:
        brain_latest = _fetchone(conn, "SELECT MAX(created_at) AS latest_at, COUNT(*) AS count FROM brain_dialogue_events")
        neuron_latest = _fetchone(
            conn,
            "SELECT MAX(created_at) AS latest_at, COUNT(*) AS count FROM brain_dialogue_events WHERE component_type = 'neuron'",
        )
        return {
            "brain_dialogue_latest_at": (brain_latest or {}).get("latest_at"),
            "neuron_dialogue_latest_at": (neuron_latest or {}).get("latest_at"),
            "brain_dialogue_events": _int((brain_latest or {}).get("count")),
            "neuron_dialogue_events": _int((neuron_latest or {}).get("count")),
        }

    def _blockers(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        rows = _fetchall(
            conn,
            """
            SELECT key AS blocker, SUM(value::int) AS count
            FROM paper_execution_runs, jsonb_each_text(block_reasons_json)
            GROUP BY key
            ORDER BY count DESC, blocker ASC
            LIMIT %s
            """,
            (limit,),
        )
        return rows

    def _power_state(self) -> dict[str, Any]:
        try:
            return self._system_power.get_power_state()
        except Exception:
            return {"system_power": "OFF", "power": "OFF", "runtime_work_allowed": False}

    def _warnings(
        self,
        power: dict[str, Any],
        safety: dict[str, int],
        integrity: dict[str, int],
        pnl: dict[str, Any],
        latest: dict[str, Any],
        live_enabled: bool,
        shadow_enabled: bool,
    ) -> list[str]:
        warnings: list[str] = []
        if safety["live_orders"] > 0:
            warnings.append("LIVE_ORDERS_PRESENT")
        if live_enabled:
            warnings.append("LIVE_TRADING_ENABLED")
        if shadow_enabled:
            warnings.append("SHADOW_TRADING_ENABLED")
        if integrity["orphan_positions_count"] > 0:
            warnings.append("ORPHAN_PAPER_POSITIONS")
        if integrity["duplicate_fills_count"] > 0:
            warnings.append("DUPLICATE_PAPER_FILLS")
        if integrity["duplicate_positions_count"] > 0:
            warnings.append("DUPLICATE_PAPER_POSITIONS")
        if integrity.get("positions_without_fills_count", 0) > 0:
            warnings.append("PAPER_POSITIONS_WITHOUT_FILLS")
        if integrity.get("positions_without_open_ledger_count", 0) > 0:
            warnings.append("PAPER_POSITIONS_WITHOUT_OPEN_LEDGER")
        if integrity.get("duplicate_intent_orders_count", 0) > 0:
            warnings.append("DUPLICATE_INTENT_PAPER_ORDERS")
        if integrity.get("duplicate_fill_positions_count", 0) > 0:
            warnings.append("DUPLICATE_FILL_PAPER_POSITIONS")
        if integrity.get("executed_intents_reexecuted_count", 0) > 0:
            warnings.append("EXECUTED_INTENTS_REEXECUTED")
        if integrity.get("paper_lineage_readiness_status") != "OK":
            warnings.append("PAPER_LINEAGE_INCONSISTENT")
        if not pnl["no_fake_pnl"]:
            warnings.append("FAKE_PNL_SUSPECTED")
        if latest.get("runtime_health") == "NO_RUNTIME_CYCLE":
            warnings.append("NO_RUNTIME_CYCLE")
        if power.get("system_power") not in {"ON", "OFF"}:
            warnings.append("SYSTEM_POWER_UNKNOWN")
        return warnings

    def _readiness_status(self, warnings: list[str]) -> str:
        red = {
            "LIVE_ORDERS_PRESENT",
            "LIVE_TRADING_ENABLED",
            "SHADOW_TRADING_ENABLED",
            "ORPHAN_PAPER_POSITIONS",
            "DUPLICATE_PAPER_FILLS",
            "DUPLICATE_PAPER_POSITIONS",
            "PAPER_POSITIONS_WITHOUT_FILLS",
            "PAPER_POSITIONS_WITHOUT_OPEN_LEDGER",
            "DUPLICATE_INTENT_PAPER_ORDERS",
            "DUPLICATE_FILL_PAPER_POSITIONS",
            "EXECUTED_INTENTS_REEXECUTED",
            "PAPER_LINEAGE_INCONSISTENT",
            "FAKE_PNL_SUSPECTED",
            "SYSTEM_POWER_UNKNOWN",
        }
        if any(item in red for item in warnings):
            return "RED"
        if warnings:
            return "YELLOW"
        return "GREEN"

    def _position_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
        opened_at = row.get("opened_at")
        latest_exit = payload.get("paper_exit_loop") if isinstance(payload.get("paper_exit_loop"), dict) else {}
        warnings = []
        if row.get("mark_price") is None and row.get("closed_at") is None:
            warnings.append("STALE_OR_MISSING_MARK_PRICE")
        for key in ("source_intent_id", "paper_order_id", "paper_fill_id"):
            if not payload.get(key):
                warnings.append(f"MISSING_{key.upper()}")
        return {
            "position_id": row.get("id"),
            "market_id": row.get("market_id"),
            "side": row.get("intended_outcome"),
            "entry_price": row.get("avg_entry"),
            "current_mark_price": row.get("mark_price"),
            "quantity": row.get("size"),
            "status": row.get("current_status"),
            "opened_at": opened_at,
            "age_seconds": (datetime.now(UTC) - opened_at).total_seconds() if hasattr(opened_at, "tzinfo") else None,
            "unrealized_pnl": row.get("unrealized"),
            "exit_plan_id": payload.get("exit_plan_id"),
            "risk_decision_id": payload.get("risk_decision_id"),
            "eligibility_id": payload.get("eligibility_id"),
            "paper_intent_id": payload.get("source_intent_id"),
            "paper_order_id": payload.get("paper_order_id"),
            "paper_fill_id": payload.get("paper_fill_id"),
            "latest_exit_check": latest_exit.get("last_checked_at"),
            "warning_flags": warnings,
        }

    def _unavailable(self, status: str, generated_at: str) -> dict[str, Any]:
        return {
            "mock_data": False,
            "generated_at": generated_at,
            "system_power": "OFF",
            "runtime_health": status,
            "paper_status": "RED",
            "warnings": [status],
            "readiness_status": "RED",
            "live_orders": 0,
            "live_enabled": False,
            "shadow_enabled": False,
        }


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return None


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def _count(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return _int(row["count"] if row else 0)


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()
    return _int(row["count"] if row else 0)


def _count_open_positions(conn: Any) -> int:
    return _count_where(
        conn,
        "paper_positions",
        "closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING') AND COALESCE(excluded_from_active_paper_truth, false) = false",
    )


def _count_executable_intents(conn: Any) -> int:
    if not _table_exists(conn, "paper_intents"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM paper_intents
        WHERE intent_status = 'CREATED'
          AND intent_type = 'PAPER_ENTRY_INTENT'
          AND paper_only = true
          AND live = false
          AND execution_allowed = false
          AND order_intent_created = false
          AND COALESCE(is_dry_run_generated, false) = false
          AND market_id IS NOT NULL
          AND side IN ('YES', 'NO')
          AND intended_price IS NOT NULL
          AND orderbook_snapshot_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM paper_fills pf
              WHERE pf.source_intent_id = paper_intents.paper_intent_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM paper_orders po
              WHERE po.payload_json->>'source_intent_id' = paper_intents.paper_intent_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM paper_positions pp
              WHERE pp.payload_json->>'source_intent_id' = paper_intents.paper_intent_id
          )
        """
    ).fetchone()
    return _int(row["count"] if row else 0)


def _max_ts(conn: Any, table: str, column: str) -> Any:
    if not _table_exists(conn, table):
        return None
    row = conn.execute(f"SELECT MAX({column}) AS ts FROM {table}").fetchone()
    return row["ts"] if row else None


def _orphan_positions(conn: Any) -> int:
    missing_source = _count_where(
        conn,
        "paper_positions",
        """
        payload_json->>'paper_fill_id' IS NOT NULL
        AND
        NOT EXISTS (
            SELECT 1 FROM paper_fills pf
            WHERE pf.paper_fill_id = paper_positions.payload_json->>'paper_fill_id'
        )
        """,
    )
    missing_close = _count_where(
        conn,
        "paper_positions",
        """
        (current_status = 'CLOSED' OR closed_at IS NOT NULL)
        AND NOT EXISTS (
            SELECT 1 FROM paper_position_closes ppc WHERE ppc.position_id = paper_positions.id
        )
        """,
    )
    return missing_source + missing_close


def _positions_without_fills(conn: Any, *, include_quarantined: bool = False) -> int:
    quarantine_filter = "" if include_quarantined else "AND COALESCE(excluded_from_active_paper_truth, false) = false"
    return _count_where(
        conn,
        "paper_positions",
        f"""
        (
        payload_json->>'paper_fill_id' IS NULL
        OR NOT EXISTS (
            SELECT 1 FROM paper_fills pf
            WHERE pf.paper_fill_id = paper_positions.payload_json->>'paper_fill_id'
        )
        )
        {quarantine_filter}
        """,
    )


def _fills_without_orders(conn: Any) -> int:
    return _count_where(
        conn,
        "paper_fills",
        """
        NOT EXISTS (
            SELECT 1 FROM paper_orders po
            WHERE po.id = paper_fills.paper_order_id
        )
        """,
    )


def _positions_without_open_ledger(conn: Any, *, include_quarantined: bool = False) -> int:
    quarantine_filter = "" if include_quarantined else "AND COALESCE(excluded_from_active_paper_truth, false) = false"
    return _count_where(
        conn,
        "paper_positions",
        f"""
        NOT EXISTS (
            SELECT 1 FROM paper_trade_ledger ptl
            WHERE ptl.position_id = paper_positions.id
              AND ptl.event_type = 'OPEN'
        )
        {quarantine_filter}
        """,
    )


def _quarantined_positions_count(conn: Any) -> int:
    return _count_where(conn, "paper_positions", "COALESCE(excluded_from_active_paper_truth, false) = true")


def _quarantined_positions(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_positions"):
        return []
    return _fetchall(
        conn,
        """
        SELECT id::text AS paper_position_id, market_id, intended_outcome AS side,
               avg_entry AS entry_price, size AS quantity, opened_at,
               invalidated_at, quarantine_reason, quarantine_source, quarantine_run_id
        FROM paper_positions
        WHERE COALESCE(excluded_from_active_paper_truth, false) = true
        ORDER BY invalidated_at DESC NULLS LAST, opened_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def _closed_positions_without_close(conn: Any) -> int:
    return _count_where(
        conn,
        "paper_positions",
        """
        (current_status = 'CLOSED' OR closed_at IS NOT NULL)
        AND NOT EXISTS (
            SELECT 1 FROM paper_position_closes ppc
            WHERE ppc.position_id = paper_positions.id
        )
        """,
    )


def _closed_positions_without_close_ledger(conn: Any) -> int:
    return _count_where(
        conn,
        "paper_positions",
        """
        (current_status = 'CLOSED' OR closed_at IS NOT NULL)
        AND NOT EXISTS (
            SELECT 1 FROM paper_trade_ledger ptl
            WHERE ptl.position_id = paper_positions.id
              AND ptl.event_type = 'CLOSE'
        )
        """,
    )


def _executed_intents_reexecuted(conn: Any) -> int:
    if not _table_exists(conn, "paper_intents"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM paper_intents pi
        WHERE pi.intent_status IN ('EXECUTED', 'POSITION_OPENED', 'CLOSED')
          AND (
              (SELECT COUNT(*) FROM paper_orders po WHERE po.payload_json->>'source_intent_id' = pi.paper_intent_id) > 1
              OR (SELECT COUNT(*) FROM paper_fills pf WHERE pf.source_intent_id = pi.paper_intent_id) > 1
              OR (SELECT COUNT(*) FROM paper_positions pp WHERE pp.payload_json->>'source_intent_id' = pi.paper_intent_id) > 1
          )
        """
    ).fetchone()
    return _int(row["count"] if row else 0)


def _duplicate_column(conn: Any, table: str, column: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM (
            SELECT {column}
            FROM {table}
            WHERE {column} IS NOT NULL
            GROUP BY {column}
            HAVING COUNT(*) > 1
        ) duplicates
        """
    ).fetchone()
    return _int(row["count"] if row else 0)


def _duplicate_payload_source(conn: Any, table: str, payload_col: str, key: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM (
            SELECT source_id
            FROM (
                SELECT {payload_col}->>%s AS source_id
                FROM {table}
                WHERE {payload_col}->>%s IS NOT NULL
            ) sources
            GROUP BY source_id
            HAVING COUNT(*) > 1
        ) duplicates
        """,
        (key, key),
    ).fetchone()
    return _int(row["count"] if row else 0)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _decimal(*values: Any) -> Decimal:
    for value in values:
        if value is None:
            continue
        try:
            return Decimal(str(value))
        except Exception:
            continue
    return Decimal("0")


def _int(*values: Any) -> int:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return 0


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


def _unique_strings(values: list[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in output:
            output.append(text)
    return output


def _latest_of(values: list[Any]) -> Any:
    latest: datetime | None = None
    raw_latest: Any = None
    for value in values:
        if value is None:
            continue
        parsed = value if isinstance(value, datetime) else None
        if parsed is None and isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
        if parsed is None:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        if latest is None or parsed > latest:
            latest = parsed
            raw_latest = value
    return raw_latest
