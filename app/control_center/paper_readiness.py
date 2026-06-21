from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.control_center.runtime_readiness import RuntimeReadinessService
from app.control_center.candidate_event_correlation import build_event_correlation
from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    truth_envelope,
)
from app.control_center.truth_hardening import classify_freshness, truth_from_freshness
from app.control_center.unified_blockers import unified_blockers
from app.control_center.orderbook_price_readiness import build_candidate_price_path_for_candidate
from app.db.connection import DatabaseConnectionFactory
from app.repositories.runtime_state_repository import RuntimeStateRepository
from app.runtime.modes import RuntimeAction, RuntimeMode
from app.runtime.state_governor import StateGovernor
from app.runtime.system_power import SystemPower


MARKET_DATA_FRESH_SECONDS = 300
ORDERBOOK_FRESH_SECONDS = 180
CANDIDATE_FRESH_SECONDS = 600
PAPER_INTENT_FRESH_SECONDS = 600
RISK_FRESH_SECONDS = 600
EXIT_FRESH_SECONDS = 600
LIFECYCLE_FRESH_SECONDS = 600

SOURCE_MAP = {
    "runtime_readiness": "/dashboard/api/v2/control/runtime-readiness",
    "paper_simulation": "system_state.metadata_json.paper_simulation",
    "paper_eligibility_candidates": "paper_eligibility_candidates",
    "paper_intents": "paper_intents",
    "orderbook_snapshots": "orderbook_snapshots",
    "risk_decisions": "risk_decisions",
    "exit_plans": "exit_plans",
    "capital": "paper_accounts + paper_capital_ledger",
    "lifecycle_governance": "lifecycle_governance_decisions",
}


class PaperReadinessService:
    """Builds current paper readiness truth without creating paper artifacts."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        governor: StateGovernor | None = None,
        runtime_readiness: RuntimeReadinessService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._runtime_readiness = runtime_readiness or RuntimeReadinessService(
            connection_factory=self._factory,
            governor=self._governor,
        )
        self._states = RuntimeStateRepository()

    def get_readiness(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(
                self._base_payload(
                    now=now,
                    blockers=["UNKNOWN_READINESS_SOURCE"],
                    warnings=["Paper readiness source is unavailable because the database is not configured."],
                    errors=[],
                ),
                status=ControlCenterStatus.MISSING,
            )

        blockers: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []
        runtime = self._runtime_payload()

        try:
            with self._factory.connect() as conn:
                state = self._states.get_current_state(conn)
                paper_simulation = self._paper_simulation_state(state)
                governor_allows_paper = self._governor_allows_paper(state)
                market = self._market_data(conn, now)
                orderbook = self._orderbook_data(conn, now)
                trusted_orderbook = self._trusted_orderbook_data(conn, now)
                price_path = self._price_path_data(conn, now)
                candidate_event_correlation = self._candidate_event_correlation_data(conn, now)
                candidates = self._candidate_data(conn, now)
                intents = self._intent_data(conn, now)
                risk = self._risk_data(conn, now)
                exit_plan = self._exit_data(conn, now)
                capital = self._capital_data(conn)
                lifecycle = self._lifecycle_data(conn, now)
                ledger = self._paper_ledger_data(conn)
        except Exception as exc:
            payload = self._base_payload(
                now=now,
                blockers=["UNKNOWN_READINESS_SOURCE"],
                warnings=warnings,
                errors=[f"Paper readiness query failed: {type(exc).__name__}: {exc}"],
            )
            return self._enveloped(payload, status=ControlCenterStatus.ERROR)

        system_power_state = self._system_power_state(state)
        runtime_life_state = str(runtime.get("runtime_life_state") or "UNKNOWN")

        if system_power_state != "ON":
            blockers.append("SYSTEM_POWER_OFF")
        if runtime_life_state not in {"ALIVE"}:
            blockers.append(self._runtime_blocker(runtime_life_state, runtime))
        if paper_simulation["paper_simulation_state"] == "OFF":
            blockers.append("PAPER_SIMULATION_OFF")
        elif paper_simulation["paper_simulation_state"] == "BLOCKED":
            blockers.append("PAPER_SIMULATION_OFF")
        elif paper_simulation["paper_simulation_state"] == "UNKNOWN":
            blockers.append("UNKNOWN_READINESS_SOURCE")
        if not governor_allows_paper:
            blockers.append("GOVERNOR_DENIED_PAPER")

        if market["state"] == "MISSING":
            blockers.append("MISSING_MARKET_DATA")
        elif market["state"] == "STALE":
            blockers.append("STALE_MARKET_DATA")
        if orderbook["state"] == "MISSING":
            blockers.append("MISSING_ORDERBOOK")
        elif orderbook["state"] == "STALE":
            blockers.append("STALE_ORDERBOOK")
        if trusted_orderbook["state"] == "MISSING":
            blockers.append("MISSING_TRUSTED_ORDERBOOK")
        elif trusted_orderbook["state"] == "STALE":
            blockers.append("STALE_TRUSTED_ORDERBOOK")
        if price_path["price_ready_candidates"] == 0 and price_path["candidates_checked"] > 0:
            blockers.extend(price_path["blockers"])

        if candidates["candidate_state"] == "NO_ELIGIBLE":
            blockers.append("NO_ELIGIBLE_CANDIDATES")
        elif candidates["candidate_state"] == "ONLY_BLOCKED":
            blockers.append("ONLY_BLOCKED_CANDIDATES")
        elif candidates["candidate_state"] == "STALE":
            blockers.append("STALE_PAPER_CANDIDATE")
        elif candidates["candidate_state"] == "UNKNOWN":
            blockers.append("UNKNOWN_READINESS_SOURCE")

        if intents["intent_state"] == "NO_INTENTS":
            blockers.append("NO_FRESH_PAPER_INTENTS")
        elif intents["intent_state"] == "ONLY_STALE_INTENTS":
            blockers.append("ONLY_STALE_PAPER_INTENTS")
        elif intents["intent_state"] == "UNKNOWN":
            blockers.append("UNKNOWN_READINESS_SOURCE")

        blockers.extend(intents["execution_blockers"])

        if risk["risk_state"] == "BLOCKED":
            blockers.append("RISK_BLOCKED")
        elif risk["risk_state"] != "APPROVED":
            blockers.append("RISK_NOT_APPROVED")
        if exit_plan["exit_state"] != "READY":
            blockers.append("EXIT_NOT_READY")
        if capital["capital_state"] == "BLOCKED":
            blockers.append("CAPITAL_NOT_OK")
        elif capital["capital_state"] != "OK":
            blockers.append("CAPITAL_NOT_OK")
        if lifecycle["lifecycle_state"] == "DENIED":
            blockers.append("LIFECYCLE_GOVERNANCE_DENIED")
        elif lifecycle["lifecycle_state"] != "ALLOWED":
            blockers.append("LIFECYCLE_GOVERNANCE_DENIED")

        blockers = _unique(blockers)
        warnings = _unique([*warnings, *runtime.get("warnings", []), *paper_simulation["warnings"]])

        execution_state = self._execution_readiness_state(
            blockers=blockers,
            runtime_life_state=runtime_life_state,
            candidate_state=candidates["candidate_state"],
            intent_state=intents["intent_state"],
        )
        readiness_state = self._paper_readiness_state(
            blockers=blockers,
            execution_state=execution_state,
            candidate_state=candidates["candidate_state"],
            intent_state=intents["intent_state"],
        )

        freshest = _latest_of(
            [
                market["latest_at"],
                orderbook["latest_at"],
                trusted_orderbook["latest_at"],
                candidates["latest_at"],
                intents["latest_at"],
            ]
        )
        freshness_state, age = classify_freshness(freshest, stale_after_seconds=ORDERBOOK_FRESH_SECONDS, now=now)
        truth_state = self._truth_state(readiness_state, freshness_state, freshest)

        payload = {
            **self._base_payload(now=now, blockers=blockers, warnings=warnings, errors=errors),
            "paper_readiness_state": readiness_state,
            "paper_execution_readiness_state": execution_state,
            "paper_simulation_state": paper_simulation["paper_simulation_state"],
            "runtime_life_state": runtime_life_state,
            "system_power_state": system_power_state,
            "governor_allows_paper": governor_allows_paper,
            "market_data_state": market["state"],
            "orderbook_state": orderbook["state"],
            "trusted_orderbook_state": trusted_orderbook["state"],
            "price_path_state": price_path["price_path_state"],
            "candidate_targeted_refresh_state": price_path["candidate_targeted_refresh_state"],
            "refresh_before_execution_state": price_path["refresh_before_execution_state"],
            "candidate_event_correlation_state": candidate_event_correlation["state"],
            "candidate_state": candidates["candidate_state"],
            "intent_state": intents["intent_state"],
            "risk_state": risk["risk_state"],
            "exit_state": exit_plan["exit_state"],
            "capital_state": capital["capital_state"],
            "lifecycle_state": lifecycle["lifecycle_state"],
            "latest_market_snapshot_at": _iso(market["latest_at"]),
            "latest_orderbook_snapshot_at": _iso(orderbook["latest_at"]),
            "latest_eligible_candidate_at": _iso(candidates["latest_eligible_at"]),
            "latest_paper_intent_at": _iso(intents["latest_at"]),
            "latest_paper_order_at": _iso(ledger["latest_order_at"]),
            "latest_paper_fill_at": _iso(ledger["latest_fill_at"]),
            "latest_paper_position_at": _iso(ledger["latest_position_at"]),
            "counts": {
                "eligible_candidates": candidates["eligible_candidates"],
                "blocked_candidates": candidates["blocked_candidates"],
                "fresh_intents": intents["fresh_intents"],
                "stale_intents": intents["stale_intents"],
                "open_positions": ledger["open_positions"],
                "paper_orders": ledger["paper_orders"],
                "paper_fills": ledger["paper_fills"],
                "price_ready_candidates": price_path["price_ready_candidates"],
                "candidates_waiting_for_orderbook_refresh": price_path["waiting_for_refresh"],
                "candidate_price_ready_count": price_path["candidate_price_ready_count"],
                "candidates_waiting_for_price_refresh": price_path["candidates_waiting_for_price_refresh"],
                "candidates_with_trusted_fresh_orderbook": price_path["candidates_with_trusted_fresh_orderbook"],
                "candidates_with_stale_orderbook": price_path["candidates_with_stale_orderbook"],
                "candidate_scoped_event_count": candidate_event_correlation["candidate_scoped_event_count"],
                "market_scoped_event_count": candidate_event_correlation["market_scoped_event_count"],
                "unlinked_event_count": candidate_event_correlation["unlinked_event_count"],
                "ambiguous_event_count": candidate_event_correlation["ambiguous_event_count"],
            },
            "required_to_be_ready": self._required_to_be_ready(blockers),
            "unified_blockers": unified_blockers(blockers, source="paper_readiness"),
            "source": SOURCE_MAP,
            "truth_state": truth_state.value,
            "freshness_state": freshness_state.value,
            "readiness_state": readiness_state,
            "last_updated": _iso(freshest or now),
            "age_seconds": age,
            "runtime_readiness": runtime,
            "paper_simulation": paper_simulation,
            "source_details": {
                "market_data": market,
                "orderbook": orderbook,
                "trusted_orderbook": trusted_orderbook,
                "price_path": price_path,
                "candidate_event_correlation": candidate_event_correlation,
                "candidates": candidates,
                "intents": intents,
                "risk": risk,
                "exit": exit_plan,
                "capital": capital,
                "lifecycle": lifecycle,
                "ledger": ledger,
            },
        }
        return self._enveloped(payload, status=self._status(readiness_state, freshness_state, errors))

    def _runtime_payload(self) -> dict[str, Any]:
        try:
            payload = self._runtime_readiness.get_readiness()
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            return data or payload
        except Exception as exc:
            return {
                "runtime_life_state": "UNKNOWN",
                "blockers": ["UNKNOWN_READINESS_SOURCE"],
                "warnings": [f"Runtime readiness source failed: {type(exc).__name__}: {exc}"],
            }

    def _paper_simulation_state(self, state: Any | None) -> dict[str, Any]:
        warnings: list[str] = []
        if state is None:
            return {"paper_simulation_state": "UNKNOWN", "enabled": False, "warnings": ["Runtime state missing."]}
        metadata = dict(state.metadata_json or {})
        paper_meta = dict(metadata.get("paper_simulation") or {})
        enabled = bool(paper_meta.get("enabled"))
        if state.current_mode == RuntimeMode.KILL or state.kill_switch_active:
            return {"paper_simulation_state": "BLOCKED", "enabled": False, "warnings": ["KILL is active."]}
        if state.system_power == SystemPower.OFF:
            enabled = False
            warnings.append("System power is OFF; paper simulation cannot run.")
        return {
            "paper_simulation_state": "ON" if enabled else "OFF",
            "enabled": enabled,
            "last_changed_at": _iso(paper_meta.get("last_changed_at") or state.last_transition_at),
            "source": SOURCE_MAP["paper_simulation"],
            "warnings": warnings,
        }

    def _governor_allows_paper(self, state: Any | None) -> bool:
        if state is None:
            return False
        try:
            return bool(self._governor.can_execute(RuntimeAction.RUN_PAPER_SIMULATION))
        except Exception:
            return False

    def _market_data(self, conn: Any, now: datetime) -> dict[str, Any]:
        latest = _max_existing_timestamp(conn, "market_snapshots_v2", ("captured_at", "snapshot_at", "collected_at", "created_at"))
        if latest is None:
            latest = _max_existing_timestamp(conn, "market_snapshots", ("captured_at", "snapshot_at", "collected_at", "created_at"))
        freshness, age = classify_freshness(latest, stale_after_seconds=MARKET_DATA_FRESH_SECONDS, now=now)
        return {"state": _data_state(freshness), "latest_at": latest, "age_seconds": age, "source": "market_snapshots_v2|market_snapshots"}

    def _orderbook_data(self, conn: Any, now: datetime) -> dict[str, Any]:
        latest = _max_existing_timestamp(conn, "orderbook_snapshots", ("snapshot_at", "collected_at"))
        freshness, age = classify_freshness(latest, stale_after_seconds=ORDERBOOK_FRESH_SECONDS, now=now)
        return {"state": _data_state(freshness), "latest_at": latest, "age_seconds": age, "source": SOURCE_MAP["orderbook_snapshots"]}

    def _trusted_orderbook_data(self, conn: Any, now: datetime) -> dict[str, Any]:
        if not _table_exists(conn, "orderbook_snapshots"):
            return {"state": "MISSING", "latest_at": None, "age_seconds": None, "source": SOURCE_MAP["orderbook_snapshots"]}
        latest = _fetch_scalar(
            conn,
            """
            SELECT MAX(COALESCE(snapshot_at, collected_at)) AS ts
            FROM orderbook_snapshots
            WHERE COALESCE(is_stale, false) = false
              AND snapshot_status IN ('OK', 'PARTIAL')
              AND (best_ask IS NOT NULL OR mid_price IS NOT NULL)
            """,
        )
        freshness, age = classify_freshness(latest, stale_after_seconds=ORDERBOOK_FRESH_SECONDS, now=now)
        return {"state": _data_state(freshness), "latest_at": latest, "age_seconds": age, "source": SOURCE_MAP["orderbook_snapshots"]}

    def _price_path_data(self, conn: Any, now: datetime) -> dict[str, Any]:
        if not _table_exists(conn, "paper_eligibility_candidates"):
            return {
                "price_path_state": "UNKNOWN",
                "candidate_targeted_refresh_state": "UNKNOWN",
                "refresh_before_execution_state": "UNKNOWN",
                "candidates_checked": 0,
                "price_ready_candidates": 0,
                "candidate_price_ready_count": 0,
                "candidates_waiting_for_price_refresh": 0,
                "candidates_with_trusted_fresh_orderbook": 0,
                "candidates_with_stale_orderbook": 0,
                "waiting_for_refresh": 0,
                "blockers": ["UNKNOWN_READINESS_SOURCE"],
                "items": [],
            }
        rows = _fetchall(
            conn,
            """
            SELECT pec.*, m.question, m.yes_token_id, m.no_token_id, m.condition_id
            FROM paper_eligibility_candidates pec
            LEFT JOIN markets_v2 m ON m.market_id = pec.market_id
            WHERE pec.status = 'ELIGIBLE'
            ORDER BY COALESCE(pec.updated_at, pec.created_at) DESC NULLS LAST, pec.id DESC
            LIMIT 100
            """,
        )
        items = [build_candidate_price_path_for_candidate(conn, row, now=now) for row in rows]
        ready = sum(1 for item in items if item.get("price_path_state") == "PRICE_READY")
        candidate_ready = sum(1 for item in items if item.get("candidate_price_path_state") == "CANDIDATE_PRICE_READY")
        waiting = sum(1 for item in items if item.get("price_path_state") == "WAITING_FOR_ORDERBOOK_REFRESH")
        candidate_waiting = sum(1 for item in items if item.get("candidate_price_path_state") in {"CANDIDATE_STALE_ORDERBOOK", "CANDIDATE_MISSING_ORDERBOOK", "CANDIDATE_REFRESH_AVAILABLE"})
        trusted_fresh = sum(1 for item in items if item.get("candidate_trusted_orderbook_state") == "TRUSTED_FRESH_FOR_CANDIDATE")
        trusted_stale = sum(1 for item in items if item.get("candidate_trusted_orderbook_state") == "TRUSTED_STALE_FOR_CANDIDATE")
        blockers = _unique([blocker for item in items for blocker in (item.get("blockers") or [])])
        refresh_states = {str(item.get("refresh_before_execution_state") or "UNKNOWN") for item in items}
        if ready:
            state = "PRICE_READY"
        elif waiting:
            state = "WAITING_FOR_ORDERBOOK_REFRESH"
        elif items and any(item.get("price_path_state") == "BLOCKED_MISSING_ORDERBOOK" for item in items):
            state = "BLOCKED_MISSING_ORDERBOOK"
        elif items:
            state = str(items[0].get("price_path_state") or "UNKNOWN")
        else:
            state = "UNKNOWN"
        if "NOT_REQUIRED" in refresh_states:
            refresh_state = "NOT_REQUIRED"
        elif "REQUIRED" in refresh_states:
            refresh_state = "REQUIRED"
        elif "REFRESH_AVAILABLE" in refresh_states:
            refresh_state = "REFRESH_AVAILABLE"
        else:
            refresh_state = "UNKNOWN"
        candidate_targeted_state = "REFRESH_SUCCEEDED" if candidate_ready else "REFRESH_AVAILABLE" if any((item.get("refresh_plan") or {}).get("can_refresh") for item in items) else "REFRESH_BLOCKED" if items else "UNKNOWN"
        return {
            "price_path_state": state,
            "candidate_targeted_refresh_state": candidate_targeted_state,
            "refresh_before_execution_state": refresh_state,
            "candidates_checked": len(items),
            "price_ready_candidates": ready,
            "candidate_price_ready_count": candidate_ready,
            "candidates_waiting_for_price_refresh": candidate_waiting,
            "candidates_with_trusted_fresh_orderbook": trusted_fresh,
            "candidates_with_stale_orderbook": trusted_stale,
            "waiting_for_refresh": waiting,
            "blockers": blockers,
            "items": items[:10],
            "source": "orderbook_price_readiness",
        }

    def _candidate_event_correlation_data(self, conn: Any, now: datetime) -> dict[str, Any]:
        if not _table_exists(conn, "event_log") or not _table_exists(conn, "paper_eligibility_candidates"):
            return {
                "state": "UNKNOWN",
                "candidate_scoped_event_count": 0,
                "market_scoped_event_count": 0,
                "unlinked_event_count": 0,
                "ambiguous_event_count": 0,
                "latest_at": None,
                "source": "event_log + paper_eligibility_candidates",
            }
        rows = _fetchall(
            conn,
            """
            SELECT *
            FROM event_log
            WHERE event_type = 'orderbook.snapshot.created'
            ORDER BY stored_at DESC, id DESC
            LIMIT 50
            """,
        )
        items = [build_event_correlation(conn, dict(row), now=now, include_bundle=False, include_candidates=False) for row in rows]
        candidate_scoped = sum(1 for item in items if item.get("candidate_event_actionability_scope") == "CANDIDATE_SCOPED")
        market_scoped = sum(1 for item in items if item.get("candidate_event_actionability_scope") == "MARKET_SCOPED_ONLY")
        unlinked = sum(1 for item in items if item.get("candidate_event_link_state") in {"UNLINKED_WITH_REASON", "MISSING_CANDIDATE", "MISSING_EVENT"})
        ambiguous = sum(1 for item in items if item.get("candidate_event_link_state") == "AMBIGUOUS_MULTIPLE_CANDIDATES")
        if candidate_scoped:
            state = "CANDIDATE_SCOPED"
        elif market_scoped or unlinked or ambiguous:
            state = "PARTIAL"
        elif items:
            state = "UNKNOWN"
        else:
            state = "MISSING"
        return {
            "state": state,
            "candidate_scoped_event_count": candidate_scoped,
            "market_scoped_event_count": market_scoped,
            "unlinked_event_count": unlinked,
            "ambiguous_event_count": ambiguous,
            "latest_at": _latest_of([item.get("event_at") for item in items]),
            "source": "event_log + paper_eligibility_candidates",
        }

    def _candidate_data(self, conn: Any, now: datetime) -> dict[str, Any]:
        if not _table_exists(conn, "paper_eligibility_candidates"):
            return {
                "candidate_state": "UNKNOWN",
                "latest_at": None,
                "latest_eligible_at": None,
                "eligible_candidates": 0,
                "blocked_candidates": 0,
                "fresh_eligible_candidates": 0,
                "source": SOURCE_MAP["paper_eligibility_candidates"],
            }
        cutoff = now - timedelta(seconds=CANDIDATE_FRESH_SECONDS)
        totals = _fetchone(
            conn,
            """
            SELECT
              COUNT(*) FILTER (WHERE status='ELIGIBLE') AS eligible_candidates,
              COUNT(*) FILTER (WHERE status='BLOCKED') AS blocked_candidates,
              COUNT(*) FILTER (WHERE status='ELIGIBLE' AND COALESCE(updated_at, created_at) >= %s) AS fresh_eligible_candidates,
              MAX(COALESCE(updated_at, created_at)) AS latest_at,
              MAX(COALESCE(updated_at, created_at)) FILTER (WHERE status='ELIGIBLE') AS latest_eligible_at
            FROM paper_eligibility_candidates
            """,
            (cutoff,),
        ) or {}
        eligible = _int(totals.get("eligible_candidates"))
        blocked = _int(totals.get("blocked_candidates"))
        fresh_eligible = _int(totals.get("fresh_eligible_candidates"))
        latest = totals.get("latest_at")
        latest_eligible = totals.get("latest_eligible_at")
        if fresh_eligible > 0:
            state = "HAS_ELIGIBLE"
        elif eligible > 0:
            state = "STALE"
        elif blocked > 0:
            state = "ONLY_BLOCKED"
        else:
            state = "NO_ELIGIBLE"
        return {
            "candidate_state": state,
            "latest_at": latest,
            "latest_eligible_at": latest_eligible,
            "eligible_candidates": eligible,
            "blocked_candidates": blocked,
            "fresh_eligible_candidates": fresh_eligible,
            "source": SOURCE_MAP["paper_eligibility_candidates"],
        }

    def _intent_data(self, conn: Any, now: datetime) -> dict[str, Any]:
        if not _table_exists(conn, "paper_intents"):
            return {
                "intent_state": "UNKNOWN",
                "latest_at": None,
                "fresh_intents": 0,
                "stale_intents": 0,
                "execution_blockers": ["NO_FRESH_PAPER_INTENTS"],
                "source": SOURCE_MAP["paper_intents"],
            }
        cutoff = now - timedelta(seconds=PAPER_INTENT_FRESH_SECONDS)
        rows = _fetchall(
            conn,
            """
            SELECT *
            FROM paper_intents
            WHERE intent_status = 'CREATED'
              AND intent_type = 'PAPER_ENTRY_INTENT'
              AND paper_only = true
              AND live = false
              AND execution_allowed = false
              AND order_intent_created = false
              AND COALESCE(is_dry_run_generated, false) = false
            ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
            LIMIT 100
            """,
        )
        latest = _fetch_scalar(conn, "SELECT MAX(COALESCE(updated_at, created_at)) AS ts FROM paper_intents")
        fresh_rows = [row for row in rows if _timestamp(row.get("updated_at") or row.get("created_at")) and _timestamp(row.get("updated_at") or row.get("created_at")) >= cutoff]
        stale_count = max(0, len(rows) - len(fresh_rows))
        execution_blockers: list[str] = []
        executable_count = 0
        for row in fresh_rows:
            row_blockers = self._intent_execution_blockers(conn, row, now)
            if row_blockers:
                execution_blockers.extend(row_blockers)
            else:
                executable_count += 1
        if fresh_rows:
            state = "HAS_FRESH_INTENTS"
        elif rows:
            state = "ONLY_STALE_INTENTS"
            execution_blockers.extend(["STALE_PAPER_INTENT", "REFRESH_REQUIRED_BEFORE_EXECUTION"])
        else:
            state = "NO_INTENTS"
        return {
            "intent_state": state,
            "latest_at": latest,
            "fresh_intents": len(fresh_rows),
            "stale_intents": stale_count,
            "executable_intents": executable_count,
            "execution_blockers": _unique(execution_blockers),
            "source": SOURCE_MAP["paper_intents"],
        }

    def _intent_execution_blockers(self, conn: Any, intent: dict[str, Any], now: datetime) -> list[str]:
        blockers: list[str] = []
        for key, code in {
            "market_id": "MISSING_MARKET_DATA",
            "side": "MISSING_SIDE",
            "risk_decision_id": "RISK_NOT_APPROVED",
            "exit_plan_id": "EXIT_NOT_READY",
        }.items():
            if intent.get(key) in (None, "", []):
                blockers.append(code)
        orderbook = self._orderbook_for_intent(conn, intent, now)
        if orderbook is None:
            blockers.append("MISSING_TRUSTED_ORDERBOOK")
        else:
            fill_price = _decimal_or_none(orderbook.get("best_ask")) or _decimal_or_none(orderbook.get("mid_price"))
            intended_price = _decimal_or_none(intent.get("intended_price"))
            if intended_price is None:
                blockers.append("MISSING_EXECUTABLE_PRICE")
            elif fill_price is not None and fill_price > intended_price + _max_slippage(intent):
                blockers.append("EXECUTION_NOT_MARKETABLE")
        quantity = _quantity_from_intent(intent)
        if quantity is None or quantity <= 0:
            blockers.append("MISSING_QUANTITY")
        return blockers

    def _orderbook_for_intent(self, conn: Any, intent: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        if not _table_exists(conn, "orderbook_snapshots"):
            return None
        snapshot_id = intent.get("orderbook_snapshot_id")
        if snapshot_id is None:
            return None
        row = conn.execute(
            """
            SELECT *
            FROM orderbook_snapshots
            WHERE id = %s
              AND market_id = %s
              AND COALESCE(is_stale, false) = false
              AND snapshot_status IN ('OK', 'PARTIAL')
              AND COALESCE(snapshot_at, collected_at, created_at) >= %s
            LIMIT 1
            """,
            (snapshot_id, intent.get("market_id"), now - timedelta(seconds=ORDERBOOK_FRESH_SECONDS)),
        ).fetchone()
        return dict(row) if row else None

    def _risk_data(self, conn: Any, now: datetime) -> dict[str, Any]:
        if not _table_exists(conn, "risk_decisions"):
            return {"risk_state": "UNKNOWN", "latest_at": None, "source": SOURCE_MAP["risk_decisions"]}
        cutoff = now - timedelta(seconds=RISK_FRESH_SECONDS)
        row = _fetchone(
            conn,
            """
            SELECT
              COUNT(*) FILTER (WHERE COALESCE(risk_approved, false) = true AND COALESCE(updated_at, created_at) >= %s) AS fresh_approved,
              COUNT(*) FILTER (WHERE decision IN ('BLOCK', 'REJECT') AND COALESCE(updated_at, created_at) >= %s) AS fresh_blocked,
              MAX(COALESCE(updated_at, created_at)) AS latest_at
            FROM risk_decisions
            """,
            (cutoff, cutoff),
        ) or {}
        approved = _int(row.get("fresh_approved"))
        blocked = _int(row.get("fresh_blocked"))
        if approved > 0:
            state = "APPROVED"
        elif blocked > 0:
            state = "BLOCKED"
        elif row.get("latest_at"):
            state = "PARTIAL"
        else:
            state = "UNKNOWN"
        return {"risk_state": state, "latest_at": row.get("latest_at"), "fresh_approved": approved, "fresh_blocked": blocked, "source": SOURCE_MAP["risk_decisions"]}

    def _exit_data(self, conn: Any, now: datetime) -> dict[str, Any]:
        if not _table_exists(conn, "exit_plans"):
            return {"exit_state": "UNKNOWN", "latest_at": None, "source": SOURCE_MAP["exit_plans"]}
        cutoff = now - timedelta(seconds=EXIT_FRESH_SECONDS)
        row = _fetchone(
            conn,
            """
            SELECT
              COUNT(*) FILTER (WHERE COALESCE(paper_exit_ready, false) = true AND COALESCE(updated_at, created_at) >= %s) AS fresh_ready,
              COUNT(*) FILTER (WHERE status IN ('BLOCKED', 'INCOMPLETE') AND COALESCE(updated_at, created_at) >= %s) AS fresh_not_ready,
              MAX(COALESCE(updated_at, created_at)) AS latest_at
            FROM exit_plans
            """,
            (cutoff, cutoff),
        ) or {}
        ready = _int(row.get("fresh_ready"))
        not_ready = _int(row.get("fresh_not_ready"))
        if ready > 0:
            state = "READY"
        elif not_ready > 0:
            state = "NOT_READY"
        elif row.get("latest_at"):
            state = "PARTIAL"
        else:
            state = "UNKNOWN"
        return {"exit_state": state, "latest_at": row.get("latest_at"), "fresh_ready": ready, "fresh_not_ready": not_ready, "source": SOURCE_MAP["exit_plans"]}

    def _capital_data(self, conn: Any) -> dict[str, Any]:
        if not _table_exists(conn, "paper_accounts"):
            return {"capital_state": "UNKNOWN", "source": SOURCE_MAP["capital"], "reason": "PAPER_ACCOUNT_MISSING"}
        account = _fetchone(
            conn,
            """
            SELECT *
            FROM paper_accounts
            WHERE account_id = 'paper_default'
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
        )
        if not account:
            return {"capital_state": "UNKNOWN", "source": SOURCE_MAP["capital"], "reason": "PAPER_ACCOUNT_MISSING"}
        active_open = _count_where(
            conn,
            "paper_positions",
            "closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING') AND COALESCE(excluded_from_active_paper_truth, false) = false",
        )
        max_open = _int(account.get("max_open_positions"))
        available = _decimal_or_none(account.get("available_balance")) or Decimal("0")
        if max_open > 0 and active_open >= max_open:
            return {"capital_state": "BLOCKED", "source": SOURCE_MAP["capital"], "reason": "MAX_OPEN_POSITIONS"}
        if available <= 0:
            return {"capital_state": "BLOCKED", "source": SOURCE_MAP["capital"], "reason": "CAPITAL_NOT_OK"}
        return {"capital_state": "OK", "source": SOURCE_MAP["capital"], "available_balance": float(available), "active_open_positions": active_open}

    def _lifecycle_data(self, conn: Any, now: datetime) -> dict[str, Any]:
        if not _table_exists(conn, "lifecycle_governance_decisions"):
            return {"lifecycle_state": "UNKNOWN", "latest_at": None, "source": SOURCE_MAP["lifecycle_governance"]}
        cutoff = now - timedelta(seconds=LIFECYCLE_FRESH_SECONDS)
        row = _fetchone(
            conn,
            """
            SELECT
              COUNT(*) FILTER (WHERE allow_paper_execution = true AND created_at >= %s) AS fresh_allowed,
              COUNT(*) FILTER (WHERE allow_paper_execution = false AND created_at >= %s) AS fresh_denied,
              MAX(created_at) AS latest_at
            FROM lifecycle_governance_decisions
            WHERE subject_type IN ('PAPER_INTENT', 'PAPER_CANDIDATE')
            """,
            (cutoff, cutoff),
        ) or {}
        allowed = _int(row.get("fresh_allowed"))
        denied = _int(row.get("fresh_denied"))
        if allowed > 0:
            state = "ALLOWED"
        elif denied > 0:
            state = "DENIED"
        elif row.get("latest_at"):
            state = "PARTIAL"
        else:
            state = "UNKNOWN"
        return {"lifecycle_state": state, "latest_at": row.get("latest_at"), "fresh_allowed": allowed, "fresh_denied": denied, "source": SOURCE_MAP["lifecycle_governance"]}

    def _paper_ledger_data(self, conn: Any) -> dict[str, Any]:
        return {
            "latest_order_at": _max_existing_timestamp(conn, "paper_orders", ("created_at", "updated_at")),
            "latest_fill_at": _max_existing_timestamp(conn, "paper_fills", ("created_at", "updated_at")),
            "latest_position_at": _max_existing_timestamp(conn, "paper_positions", ("opened_at", "created_at", "updated_at")),
            "open_positions": _count_where(conn, "paper_positions", "closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING') AND COALESCE(excluded_from_active_paper_truth, false) = false"),
            "paper_orders": _count_table(conn, "paper_orders"),
            "paper_fills": _count_table(conn, "paper_fills"),
            "source": "paper_orders + paper_fills + paper_positions",
        }

    def _base_payload(self, *, now: datetime, blockers: list[str], warnings: list[str], errors: list[str]) -> dict[str, Any]:
        return {
            "paper_readiness_state": "UNKNOWN",
            "paper_execution_readiness_state": "UNKNOWN",
            "paper_simulation_state": "UNKNOWN",
            "runtime_life_state": "UNKNOWN",
            "system_power_state": "UNKNOWN",
            "governor_allows_paper": False,
            "market_data_state": "UNKNOWN",
            "orderbook_state": "UNKNOWN",
            "trusted_orderbook_state": "UNKNOWN",
            "price_path_state": "UNKNOWN",
            "candidate_targeted_refresh_state": "UNKNOWN",
            "refresh_before_execution_state": "UNKNOWN",
            "candidate_state": "UNKNOWN",
            "intent_state": "UNKNOWN",
            "risk_state": "UNKNOWN",
            "exit_state": "UNKNOWN",
            "capital_state": "UNKNOWN",
            "lifecycle_state": "UNKNOWN",
            "latest_market_snapshot_at": None,
            "latest_orderbook_snapshot_at": None,
            "latest_eligible_candidate_at": None,
            "latest_paper_intent_at": None,
            "latest_paper_order_at": None,
            "latest_paper_fill_at": None,
            "latest_paper_position_at": None,
            "counts": {
                "eligible_candidates": 0,
                "blocked_candidates": 0,
                "fresh_intents": 0,
                "stale_intents": 0,
                "open_positions": 0,
                "paper_orders": 0,
                "paper_fills": 0,
                "price_ready_candidates": 0,
                "candidates_waiting_for_orderbook_refresh": 0,
                "candidate_price_ready_count": 0,
                "candidates_waiting_for_price_refresh": 0,
                "candidates_with_trusted_fresh_orderbook": 0,
                "candidates_with_stale_orderbook": 0,
            },
            "blockers": _unique(blockers),
            "warnings": _unique(warnings),
            "errors": list(errors),
            "required_to_be_ready": self._required_to_be_ready(blockers),
            "source": SOURCE_MAP,
            "truth_state": ControlCenterTruthState.UNKNOWN.value,
            "freshness_state": ControlCenterFreshnessState.MISSING.value,
            "readiness_state": "UNKNOWN",
            "last_updated": now.isoformat(),
            "generated_at": now.isoformat(),
        }

    def _paper_readiness_state(self, *, blockers: list[str], execution_state: str, candidate_state: str, intent_state: str) -> str:
        if not blockers and execution_state == "EXECUTABLE":
            return "READY"
        if any(item in blockers for item in ("SYSTEM_POWER_OFF", "RUNTIME_NOT_ALIVE", "RUNTIME_STOPPED", "RUNTIME_STALE", "PAPER_SIMULATION_OFF", "GOVERNOR_DENIED_PAPER")):
            return "BLOCKED"
        if candidate_state == "HAS_ELIGIBLE" and intent_state in {"NO_INTENTS", "ONLY_STALE_INTENTS"}:
            return "PARTIAL"
        if execution_state.startswith("BLOCKED_BY_"):
            return "BLOCKED"
        if "UNKNOWN_READINESS_SOURCE" in blockers:
            return "UNKNOWN"
        return "NOT_READY"

    def _execution_readiness_state(self, *, blockers: list[str], runtime_life_state: str, candidate_state: str, intent_state: str) -> str:
        if not blockers and intent_state == "HAS_FRESH_INTENTS":
            return "EXECUTABLE"
        if "GOVERNOR_DENIED_PAPER" in blockers:
            return "BLOCKED_BY_GOVERNOR"
        if any(item in blockers for item in ("RUNTIME_NOT_ALIVE", "RUNTIME_STOPPED", "RUNTIME_STALE")) or runtime_life_state != "ALIVE":
            return "BLOCKED_BY_RUNTIME"
        if any(item in blockers for item in ("MISSING_MARKET_DATA", "STALE_MARKET_DATA", "MISSING_ORDERBOOK", "STALE_ORDERBOOK", "MISSING_TRUSTED_ORDERBOOK", "STALE_TRUSTED_ORDERBOOK", "BLOCKED_MISSING_TOKEN", "BLOCKED_MISSING_SIDE", "BLOCKED_UNTRUSTED_SOURCE", "MISSING_EXECUTABLE_PRICE")):
            return "BLOCKED_BY_DATA"
        if any(item in blockers for item in ("RISK_NOT_APPROVED", "RISK_BLOCKED")):
            return "BLOCKED_BY_RISK"
        if "EXIT_NOT_READY" in blockers:
            return "BLOCKED_BY_EXIT"
        if "CAPITAL_NOT_OK" in blockers or "MAX_OPEN_POSITIONS" in blockers:
            return "BLOCKED_BY_CAPITAL"
        if "LIFECYCLE_GOVERNANCE_DENIED" in blockers:
            return "BLOCKED_BY_LIFECYCLE"
        if candidate_state == "HAS_ELIGIBLE" and intent_state in {"NO_INTENTS", "ONLY_STALE_INTENTS"}:
            return "WAITING_FOR_REFRESH"
        if blockers:
            return "NOT_EXECUTABLE"
        return "UNKNOWN"

    def _required_to_be_ready(self, blockers: list[str]) -> list[str]:
        labels = {
            "SYSTEM_POWER_OFF": "System power must be ON.",
            "RUNTIME_NOT_ALIVE": "Runtime readiness must be ALIVE.",
            "RUNTIME_STOPPED": "Runtime must be running.",
            "RUNTIME_STALE": "Runtime must refresh successfully.",
            "PAPER_SIMULATION_OFF": "Paper Simulation must be ON.",
            "GOVERNOR_DENIED_PAPER": "State Governor must allow RUN_PAPER_SIMULATION.",
            "NO_ELIGIBLE_CANDIDATES": "At least one fresh eligible candidate is required.",
            "ONLY_BLOCKED_CANDIDATES": "At least one candidate must pass eligibility.",
            "STALE_PAPER_CANDIDATE": "Eligible candidate evidence must be fresh.",
            "NO_FRESH_PAPER_INTENTS": "A fresh paper intent is required before execution.",
            "ONLY_STALE_PAPER_INTENTS": "Paper intents must be refreshed.",
            "MISSING_MARKET_DATA": "Market data must exist.",
            "STALE_MARKET_DATA": "Market data must be fresh.",
            "MISSING_ORDERBOOK": "Orderbook data must exist.",
            "STALE_ORDERBOOK": "Orderbook data must be fresh.",
            "MISSING_TRUSTED_ORDERBOOK": "Trusted orderbook must be available.",
            "STALE_TRUSTED_ORDERBOOK": "Trusted orderbook must be fresh.",
            "RISK_NOT_APPROVED": "Risk must approve.",
            "RISK_BLOCKED": "Risk blockers must clear.",
            "EXIT_NOT_READY": "Exit plan must be ready.",
            "CAPITAL_NOT_OK": "Paper capital must be OK.",
            "LIFECYCLE_GOVERNANCE_DENIED": "Lifecycle governance must allow paper.",
            "EXECUTION_NOT_MARKETABLE": "Intent price must be marketable.",
            "MISSING_EXECUTABLE_PRICE": "Executable price is required.",
            "BLOCKED_MISSING_TOKEN": "Candidate side must map to a CLOB token_id.",
            "BLOCKED_MISSING_SIDE": "Candidate must include YES or NO side.",
            "BLOCKED_UNTRUSTED_SOURCE": "Trusted orderbook source must be available.",
            "MISSING_QUANTITY": "Quantity is required.",
            "MAX_OPEN_POSITIONS": "Open position limit must have room.",
            "UNKNOWN_READINESS_SOURCE": "Unknown readiness source must be resolved.",
        }
        return [labels[item] for item in _unique(blockers) if item in labels]

    def _runtime_blocker(self, runtime_life_state: str, runtime: dict[str, Any]) -> str:
        if runtime_life_state == "STOPPED":
            return "RUNTIME_STOPPED"
        if runtime_life_state == "STALE":
            return "RUNTIME_STALE"
        if runtime_life_state == "BLOCKED":
            return "RUNTIME_NOT_ALIVE"
        if runtime.get("system_power_state") == "OFF":
            return "RUNTIME_STOPPED"
        return "RUNTIME_NOT_ALIVE"

    def _system_power_state(self, state: Any | None) -> str:
        if state is None:
            return "UNKNOWN"
        if state.current_mode == RuntimeMode.KILL or state.kill_switch_active:
            return "KILL"
        return str(state.system_power.value)

    def _truth_state(
        self,
        readiness_state: str,
        freshness_state: ControlCenterFreshnessState,
        freshest: Any,
    ) -> ControlCenterTruthState:
        if readiness_state == "READY":
            return ControlCenterTruthState.ACTIVE_FRESH
        if readiness_state in {"NOT_READY", "BLOCKED", "PARTIAL"}:
            if freshness_state == ControlCenterFreshnessState.STALE:
                return ControlCenterTruthState.REFRESH_REQUIRED
            return truth_from_freshness(freshness_state, has_history=bool(freshest))
        return ControlCenterTruthState.UNKNOWN

    def _status(self, readiness_state: str, freshness_state: ControlCenterFreshnessState, errors: list[str]) -> ControlCenterStatus:
        if errors:
            return ControlCenterStatus.ERROR
        if readiness_state == "READY":
            return ControlCenterStatus.REAL
        if readiness_state == "BLOCKED":
            return ControlCenterStatus.LOCKED
        if readiness_state == "PARTIAL":
            return ControlCenterStatus.PARTIAL
        if freshness_state == ControlCenterFreshnessState.STALE:
            return ControlCenterStatus.STALE
        if readiness_state == "UNKNOWN":
            return ControlCenterStatus.MISSING
        return ControlCenterStatus.PARTIAL

    def _enveloped(self, payload: dict[str, Any], *, status: ControlCenterStatus) -> dict[str, Any]:
        readiness = ControlCenterReadinessState(payload.get("readiness_state") if payload.get("readiness_state") in {item.value for item in ControlCenterReadinessState} else ControlCenterReadinessState.UNKNOWN)
        runtime_state = {
            "READY": ControlCenterRuntimeState.RUNNING,
            "BLOCKED": ControlCenterRuntimeState.BLOCKED,
            "PARTIAL": ControlCenterRuntimeState.STALE,
            "NOT_READY": ControlCenterRuntimeState.STOPPED,
        }.get(str(payload.get("readiness_state")), ControlCenterRuntimeState.UNKNOWN)
        envelope = truth_envelope(
            status=status,
            source="paper readiness: runtime_readiness + system_state + StateGovernor + paper/current evidence tables",
            truth_state=payload.get("truth_state") or ControlCenterTruthState.UNKNOWN,
            data=payload,
            last_updated=payload.get("last_updated"),
            stale_after_seconds=ORDERBOOK_FRESH_SECONDS,
            age_seconds=payload.get("age_seconds"),
            freshness_state=payload.get("freshness_state") or ControlCenterFreshnessState.MISSING,
            runtime_state=runtime_state,
            readiness_state=readiness,
            warnings=list(payload.get("warnings") or []),
            errors=list(payload.get("errors") or []),
        ).to_dict()
        return {**envelope, **payload}


def _data_state(freshness: ControlCenterFreshnessState) -> str:
    if freshness == ControlCenterFreshnessState.FRESH:
        return "FRESH"
    if freshness == ControlCenterFreshnessState.STALE:
        return "STALE"
    return "MISSING"


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return row is not None


def _max_existing_timestamp(conn: Any, table: str, columns: tuple[str, ...]) -> Any:
    if not _table_exists(conn, table):
        return None
    existing = [column for column in columns if _column_exists(conn, table, column)]
    if not existing:
        return None
    expression = "GREATEST(" + ", ".join(f"MAX({column})" for column in existing) + ")"
    return _fetch_scalar(conn, f"SELECT {expression} AS ts FROM {table}")


def _fetch_scalar(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    try:
        row = conn.execute(sql, params).fetchone()
        if not row:
            return None
        return row.get("ts") if hasattr(row, "get") else row[0]
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return None


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


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return _int(row["count"] if row else 0)


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    try:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()
        return _int(row["count"] if row else 0)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return 0


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _quantity_from_intent(intent: dict[str, Any]) -> Decimal | None:
    evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
    for key in ("quantity", "size", "intended_size", "open_quantity"):
        quantity = _decimal_or_none(evidence.get(key))
        if quantity is not None and quantity > 0:
            return quantity
    intended_price = _decimal_or_none(intent.get("intended_price"))
    for key in ("notional", "intended_notional"):
        notional = _decimal_or_none(evidence.get(key))
        if notional is not None and notional > 0 and intended_price is not None and intended_price > 0:
            return notional / intended_price
    return None


def _max_slippage(intent: dict[str, Any]) -> Decimal:
    value = _decimal_or_none(intent.get("max_slippage"))
    if value is None:
        return Decimal("0")
    return max(Decimal("0"), value)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    return str(value)


def _latest_of(values: list[Any]) -> Any:
    latest: datetime | None = None
    raw_latest: Any = None
    for value in values:
        parsed = _timestamp(value)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
            raw_latest = value
    return raw_latest


def _unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in output:
            output.append(text)
    return output
