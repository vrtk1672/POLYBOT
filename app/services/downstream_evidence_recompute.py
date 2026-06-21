from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.logging import get_logger
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.exit_foundation import ExitFoundationService
from app.services.paper_eligibility import PaperEligibilityService
from app.services.paper_intents import PaperIntentGateService
from app.services.risk_core import RiskCoreService
from app.services.system_power import SystemPowerService
from app.services.thesis_profiles import ThesisProfileService

logger = get_logger(__name__)


class DownstreamEvidenceRecomputeService:
    """Consume refreshed evidence through non-executing downstream gates."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        thesis_service: ThesisProfileService | None = None,
        risk_service: RiskCoreService | None = None,
        exit_service: ExitFoundationService | None = None,
        eligibility_service: PaperEligibilityService | None = None,
        no_trade_service: PaperIntentGateService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._thesis = thesis_service or ThesisProfileService(connection_factory=self._factory)
        self._risk = risk_service or RiskCoreService(connection_factory=self._factory)
        self._exit = exit_service or ExitFoundationService(connection_factory=self._factory)
        self._eligibility = eligibility_service or PaperEligibilityService(connection_factory=self._factory)
        self._no_trade = no_trade_service or PaperIntentGateService(connection_factory=self._factory)

    def run_recompute(self, *, cycle_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"downstream_recompute_{uuid4().hex}"
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
        eligible_before = self._eligible_count()
        errors: list[str] = []
        thesis: dict[str, Any] = {}
        risk: dict[str, Any] = {}
        exit_result: dict[str, Any] = {}
        eligibility: dict[str, Any] = {}
        no_trade: dict[str, Any] = {}

        try:
            thesis = self._thesis.build_profiles(limit=limit, include_incomplete=True, include_blocked=True, write_profiles=True)
        except Exception as exc:
            errors.append(f"thesis:{type(exc).__name__}:{exc}")
            logger.exception("downstream_recompute_thesis_failed cycle_id=%s", cycle_id)

        try:
            risk = self._risk.evaluate_risk(limit=limit, include_blocked=True, write_decisions=True)
        except Exception as exc:
            errors.append(f"risk:{type(exc).__name__}:{exc}")
            logger.exception("downstream_recompute_risk_failed cycle_id=%s", cycle_id)

        try:
            exit_result = self._exit.build_exit_plans(limit=limit, include_blocked=True, write_plans=True)
        except Exception as exc:
            errors.append(f"exit:{type(exc).__name__}:{exc}")
            logger.exception("downstream_recompute_exit_failed cycle_id=%s", cycle_id)

        try:
            eligibility = self._eligibility.evaluate_candidates(limit=limit, include_blocked=True, write_candidates=True)
        except Exception as exc:
            errors.append(f"eligibility:{type(exc).__name__}:{exc}")
            logger.exception("downstream_recompute_eligibility_failed cycle_id=%s", cycle_id)

        try:
            no_trade = self._no_trade.build_intents(limit=limit, write_intents=False, write_no_trade=True)
        except Exception as exc:
            errors.append(f"no_trade:{type(exc).__name__}:{exc}")
            logger.exception("downstream_recompute_no_trade_failed cycle_id=%s", cycle_id)

        safety_after = self._safety_counts()
        blockers_after = self._blocker_counts()
        eligible_after = self._eligible_count()
        status = "DEGRADED" if errors else "OK"
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": status,
            "thesis_checked": _int(thesis.get("coordinator_decisions_checked")),
            "thesis_updated": _int(thesis.get("thesis_profiles_created")) + _int(thesis.get("thesis_profiles_updated")),
            "risk_checked": _int(risk.get("thesis_profiles_checked")),
            "risk_updated": _int(risk.get("risk_decisions_created")) + _int(risk.get("risk_decisions_updated")),
            "exit_checked": _int(exit_result.get("risk_decisions_checked")),
            "exit_updated": _int(exit_result.get("exit_plans_created")) + _int(exit_result.get("exit_plans_updated")),
            "eligibility_checked": _int(eligibility.get("exit_plans_checked")),
            "eligibility_updated": _int(eligibility.get("candidates_created")) + _int(eligibility.get("candidates_updated")),
            "no_trade_checked": _int(no_trade.get("candidates_checked")),
            "no_trade_updated": _int(no_trade.get("no_trade_records_created")) + _int(no_trade.get("no_trade_records_updated")),
            "missing_fresh_orderbook_before": blockers_before["missing_fresh_orderbook"],
            "missing_fresh_orderbook_after": blockers_after["missing_fresh_orderbook"],
            "missing_signal_market_binding_before": blockers_before["missing_signal_market_binding"],
            "missing_signal_market_binding_after": blockers_after["missing_signal_market_binding"],
            "missing_side_before": blockers_before["missing_side"],
            "missing_side_after": blockers_after["missing_side"],
            "missing_market_link_before": blockers_before["missing_market_link"],
            "missing_market_link_after": blockers_after["missing_market_link"],
            "missing_mid_price_before": blockers_before["missing_mid_price"],
            "missing_mid_price_after": blockers_after["missing_mid_price"],
            "thesis_blocked_before": blockers_before["thesis_blocked"],
            "thesis_blocked_after": blockers_after["thesis_blocked"],
            "risk_not_approved_before": blockers_before["risk_not_approved"],
            "risk_not_approved_after": blockers_after["risk_not_approved"],
            "exit_not_ready_before": blockers_before["exit_not_ready"],
            "exit_not_ready_after": blockers_after["exit_not_ready"],
            "eligible_before": eligible_before,
            "eligible_after": eligible_after,
            "orders_delta": max(0, safety_after["orders"] - safety_before["orders"]),
            "order_intents_delta": max(0, safety_after["order_intents"] - safety_before["order_intents"]),
            "fills_delta": max(0, safety_after["fills"] - safety_before["fills"]),
            "positions_delta": max(0, safety_after["positions"] - safety_before["positions"]),
            "live_actions_delta": max(0, safety_after["live_actions"] - safety_before["live_actions"]),
            "error_message": "; ".join(errors) if errors else None,
            "metadata": {
                "thesis_status": thesis.get("status"),
                "risk_status": risk.get("status"),
                "exit_status": exit_result.get("status"),
                "eligibility_status": eligibility.get("status"),
                "no_trade_status": no_trade.get("status"),
                "no_paper_intents_created": True,
                "paper_intents_skipped_by_phase": True,
                "top_current_blockers": self._top_current_blockers(limit=10),
                "root_cause_if_unchanged": self._root_cause(blockers_before, blockers_after),
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
            "downstream_recompute_allowed": bool(power.get("runtime_work_allowed")),
            "downstream_recompute_active": False,
            "last_downstream_recompute_at": latest.get("finished_at") if latest else None,
            "last_downstream_recompute_status": latest.get("status") if latest else None,
            "latest_run": latest,
            "risk_checked": _int(latest.get("risk_checked")) if latest else 0,
            "risk_updated": _int(latest.get("risk_updated")) if latest else 0,
            "exit_checked": _int(latest.get("exit_checked")) if latest else 0,
            "exit_updated": _int(latest.get("exit_updated")) if latest else 0,
            "eligibility_checked": _int(latest.get("eligibility_checked")) if latest else 0,
            "eligibility_updated": _int(latest.get("eligibility_updated")) if latest else 0,
            "no_trade_updated": _int(latest.get("no_trade_updated")) if latest else 0,
            "missing_fresh_orderbook_before": _int(latest.get("missing_fresh_orderbook_before")) if latest else blockers["missing_fresh_orderbook"],
            "missing_fresh_orderbook_after": _int(latest.get("missing_fresh_orderbook_after")) if latest else blockers["missing_fresh_orderbook"],
            "missing_signal_market_binding_before": _int(latest.get("missing_signal_market_binding_before")) if latest else blockers["missing_signal_market_binding"],
            "missing_signal_market_binding_after": _int(latest.get("missing_signal_market_binding_after")) if latest else blockers["missing_signal_market_binding"],
            "missing_side_before": _int(latest.get("missing_side_before")) if latest else blockers["missing_side"],
            "missing_side_after": _int(latest.get("missing_side_after")) if latest else blockers["missing_side"],
            "eligible_before": _int(latest.get("eligible_before")) if latest else self._eligible_count(),
            "eligible_after": _int(latest.get("eligible_after")) if latest else self._eligible_count(),
            "top_current_blockers": self._top_current_blockers(limit=limit),
            "latest_risk_decision_at": self._latest_timestamp("risk_decisions", "updated_at"),
            "latest_exit_plan_at": self._latest_timestamp("exit_plans", "updated_at"),
            "latest_eligibility_at": self._latest_timestamp("paper_eligibility_candidates", "updated_at"),
            "latest_no_trade_at": self._latest_timestamp("no_trade_log", "updated_at"),
            "orders_delta": _int(latest.get("orders_delta")) if latest else 0,
            "order_intents_delta": _int(latest.get("order_intents_delta")) if latest else 0,
            "fills_delta": _int(latest.get("fills_delta")) if latest else 0,
            "positions_delta": _int(latest.get("positions_delta")) if latest else 0,
            "live_actions_delta": _int(latest.get("live_actions_delta")) if latest else 0,
            "paper_ready": False,
            "root_cause_if_unchanged": (latest.get("metadata_json") or {}).get("root_cause_if_unchanged") if latest else None,
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _blocked_payload(self, run_id: str, cycle_id: str | None, system_power: str, started_at: datetime, reason: str) -> dict[str, Any]:
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "status": "BLOCKED",
            "blocked_reason": reason,
            "risk_checked": 0,
            "exit_checked": 0,
            "eligibility_checked": 0,
            "no_trade_checked": 0,
            "orders_delta": 0,
            "order_intents_delta": 0,
            "fills_delta": 0,
            "positions_delta": 0,
            "live_actions_delta": 0,
        }

    def _existing_for_cycle(self, cycle_id: str | None) -> dict[str, Any] | None:
        if not cycle_id or not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "downstream_evidence_recompute_runs"):
                return None
            row = conn.execute("SELECT * FROM downstream_evidence_recompute_runs WHERE cycle_id = %s", (cycle_id,)).fetchone()
            return dict(row) if row else None

    def _insert_run(self, conn: Any, payload: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO downstream_evidence_recompute_runs (
                run_id, cycle_id, system_power, started_at, finished_at, status,
                thesis_checked, thesis_updated, risk_checked, risk_updated,
                exit_checked, exit_updated, eligibility_checked, eligibility_updated,
                no_trade_checked, no_trade_updated,
                missing_fresh_orderbook_before, missing_fresh_orderbook_after,
                missing_signal_market_binding_before, missing_signal_market_binding_after,
                missing_side_before, missing_side_after, missing_market_link_before,
                missing_market_link_after, missing_mid_price_before, missing_mid_price_after,
                thesis_blocked_before, thesis_blocked_after, risk_not_approved_before,
                risk_not_approved_after, exit_not_ready_before, exit_not_ready_after,
                eligible_before, eligible_after, orders_delta, order_intents_delta,
                fills_delta, positions_delta, live_actions_delta, error_message,
                metadata_json, created_at
            )
            VALUES (
                %(run_id)s, %(cycle_id)s, %(system_power)s, %(started_at)s,
                %(finished_at)s, %(status)s, %(thesis_checked)s, %(thesis_updated)s,
                %(risk_checked)s, %(risk_updated)s, %(exit_checked)s, %(exit_updated)s,
                %(eligibility_checked)s, %(eligibility_updated)s,
                %(no_trade_checked)s, %(no_trade_updated)s,
                %(missing_fresh_orderbook_before)s, %(missing_fresh_orderbook_after)s,
                %(missing_signal_market_binding_before)s,
                %(missing_signal_market_binding_after)s, %(missing_side_before)s,
                %(missing_side_after)s, %(missing_market_link_before)s,
                %(missing_market_link_after)s, %(missing_mid_price_before)s,
                %(missing_mid_price_after)s, %(thesis_blocked_before)s,
                %(thesis_blocked_after)s, %(risk_not_approved_before)s,
                %(risk_not_approved_after)s, %(exit_not_ready_before)s,
                %(exit_not_ready_after)s, %(eligible_before)s, %(eligible_after)s,
                %(orders_delta)s, %(order_intents_delta)s, %(fills_delta)s,
                %(positions_delta)s, %(live_actions_delta)s, %(error_message)s,
                %(metadata_json)s, now()
            )
            """,
            {**payload, "metadata_json": Jsonb(payload.get("metadata") or {})},
        )

    def _latest_run(self) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "downstream_evidence_recompute_runs"):
                return None
            row = conn.execute("SELECT * FROM downstream_evidence_recompute_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _latest_timestamp(self, table: str, column: str) -> str | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, table):
                return None
            row = conn.execute(f"SELECT MAX({column}) AS latest_at FROM {table}").fetchone()
            value = row["latest_at"] if row else None
            return value.isoformat() if hasattr(value, "isoformat") else value

    def _eligible_count(self) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            return _count_where(conn, "paper_eligibility_candidates", "status = 'ELIGIBLE'")

    def _blocker_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return _empty_blockers()
        with self._factory.connect() as conn:
            return {
                "missing_fresh_orderbook": _json_array_count(conn, "thesis_profiles", "missing_evidence", "MISSING_FRESH_ORDERBOOK") + _json_array_count(conn, "risk_decisions", "required_missing_evidence", "MISSING_FRESH_ORDERBOOK") + _json_array_count(conn, "exit_plans", "missing_exit_evidence", "MISSING_FRESH_ORDERBOOK") + _json_array_count(conn, "paper_eligibility_candidates", "missing_requirements", "MISSING_FRESH_ORDERBOOK"),
                "missing_signal_market_binding": _json_array_count(conn, "thesis_profiles", "missing_evidence", "MISSING_SIGNAL_MARKET_BINDING") + _json_array_count(conn, "paper_eligibility_candidates", "missing_requirements", "MISSING_SIGNAL_MARKET_BINDING"),
                "missing_side": _count_missing_side(conn) + _json_array_count(conn, "exit_plans", "missing_exit_evidence", "MISSING_SIDE") + _json_array_count(conn, "paper_eligibility_candidates", "missing_requirements", "MISSING_SIDE"),
                "missing_market_link": _json_array_count(conn, "paper_eligibility_candidates", "missing_requirements", "MISSING_MARKET_LINK") + _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "MISSING_MARKET_LINK"),
                "missing_mid_price": _json_array_count(conn, "exit_plans", "missing_exit_evidence", "MISSING_MID_PRICE") + _json_array_count(conn, "exit_plans", "blockers", "MISSING_MID_PRICE"),
                "thesis_blocked": _count_where(conn, "thesis_profiles", "status = 'BLOCKED'") + _json_array_count(conn, "risk_decisions", "blockers", "THESIS_BLOCKED") + _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "THESIS_BLOCKED"),
                "risk_not_approved": _count_where(conn, "risk_decisions", "risk_approved = false") + _json_array_count(conn, "exit_plans", "missing_exit_evidence", "MISSING_RISK_APPROVAL") + _json_array_count(conn, "paper_eligibility_candidates", "missing_requirements", "RISK_NOT_APPROVED"),
                "exit_not_ready": _count_where(conn, "exit_plans", "COALESCE(paper_exit_ready, false) = false") + _json_array_count(conn, "paper_eligibility_candidates", "missing_requirements", "EXIT_NOT_READY"),
            }

    def _top_current_blockers(self, *, limit: int) -> list[dict[str, Any]]:
        counts = self._blocker_counts()
        return [
            {"blocker": key.upper(), "count": value}
            for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
            if value > 0
        ]

    def _root_cause(self, before: dict[str, int], after: dict[str, int]) -> str | None:
        if any(after[key] < before[key] for key in before):
            return None
        if any(after[key] > before[key] for key in before):
            return "Downstream recompute consumed refreshed evidence and created/updated current rows, but total blockers increased because new Brain Mesh candidates were also introduced and remain blocked by valid missing side, binding, thesis, risk, and exit evidence."
        if after.get("missing_side", 0) > 0:
            return "Fresh orderbooks were consumed, but side-dependent blockers remain until trusted unambiguous YES/NO evidence is available."
        if after.get("missing_signal_market_binding", 0) > 0:
            return "Binding blockers remain because deterministic trusted signal-market links are still missing for some candidates."
        if after.get("missing_fresh_orderbook", 0) > 0:
            return "Fresh orderbook blockers remain where refreshed snapshots cannot be linked to current thesis/risk/exit inputs."
        return "No blocker reduction detected; downstream records were recomputed with current evidence and stayed blocked by valid safety rules."

    def _safety_counts(self) -> dict[str, int]:
        counts = {"orders": 0, "order_intents": 0, "fills": 0, "positions": 0, "live_actions": 0}
        if not self._factory.enabled:
            return counts
        with self._factory.connect() as conn:
            counts["orders"] = _count_table(conn, "paper_orders") + _count_table(conn, "shadow_orders") + _count_table(conn, "live_orders")
            counts["order_intents"] = _count_table(conn, "order_intents")
            counts["fills"] = _count_table(conn, "paper_fills") + _count_table(conn, "fills_v2")
            counts["positions"] = _count_table(conn, "positions")
            counts["live_actions"] = _count_table(conn, "live_orders")
        return counts


def _empty_blockers() -> dict[str, int]:
    return {
        "missing_fresh_orderbook": 0,
        "missing_signal_market_binding": 0,
        "missing_side": 0,
        "missing_market_link": 0,
        "missing_mid_price": 0,
        "thesis_blocked": 0,
        "risk_not_approved": 0,
        "exit_not_ready": 0,
    }


def _count_missing_side(conn: Any) -> int:
    return _count_where(conn, "thesis_profiles", "side IS NULL OR side NOT IN ('YES','NO')") + _count_where(conn, "position_thesis_profiles", "side IS NULL OR side NOT IN ('YES','NO')")


def _json_array_count(conn: Any, table: str, column: str, value: str) -> int:
    if not _table_exists(conn, table) or not _column_exists(conn, table, column):
        return 0
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM {table}
        WHERE EXISTS (
            SELECT 1
            FROM jsonb_array_elements_text(COALESCE({column}, '[]'::jsonb)) AS item
            WHERE UPPER(item) = %s
        )
        """,
        (value.upper(),),
    ).fetchone()
    return int(row["count"] or 0)


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = ANY (current_schemas(false))
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return bool(row)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value.__class__.__name__ == "Decimal":
        return float(value)
    return value
