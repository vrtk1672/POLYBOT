from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.last_mile_orderbook_refresh import (
    LastMileOrderbookRefreshService,
    is_fresh_orderbook,
    latest_matching_orderbook,
    orderbook_age_seconds,
)
from app.services.lifecycle_governance import LifecycleGovernanceGateService
from app.services.opportunity_memory import OpportunityMemoryService
from app.services.paper_capital import PaperCapitalService
from app.services.paper_defense import get_active_profile
from app.services.paper_session import active_paper_session_id
from app.services.payout_odds import PayoutOddsService
from app.services.same_market_side_guard import SameMarketSideGuardService
from app.services.system_power import SystemPowerService

FRESH_ORDERBOOK_SECONDS = 180
DEFAULT_MAX_SLIPPAGE = Decimal("0.00")


class PaperExecutionService:
    """Safely convert valid paper intents into simulated paper orders, fills, and positions."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        paper_capital: PaperCapitalService | None = None,
        same_market_guard: SameMarketSideGuardService | None = None,
        payout_odds: PayoutOddsService | None = None,
        lifecycle_governance: LifecycleGovernanceGateService | None = None,
        opportunity_memory: OpportunityMemoryService | None = None,
        last_mile_orderbook_refresh: LastMileOrderbookRefreshService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._paper_capital = paper_capital or PaperCapitalService(connection_factory=self._factory, system_power=self._system_power)
        self._same_market_guard = same_market_guard or SameMarketSideGuardService(connection_factory=self._factory)
        self._payout_odds = payout_odds or PayoutOddsService(connection_factory=self._factory)
        self._lifecycle_governance = lifecycle_governance or LifecycleGovernanceGateService(connection_factory=self._factory)
        self._opportunity_memory = opportunity_memory or OpportunityMemoryService(connection_factory=self._factory)
        self._last_mile_orderbook_refresh = last_mile_orderbook_refresh or LastMileOrderbookRefreshService()

    def run_execution(
        self,
        *,
        limit: int = 100,
        cycle_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"paper_execution_{uuid4().hex}"
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        if system_power != "ON" or not bool(power.get("runtime_work_allowed")):
            payload = self._run_payload(run_id, cycle_id, system_power, started_at, "SYSTEM_POWER_OFF")
            return _json_safe(payload)
        if not self._factory.enabled:
            payload = self._run_payload(run_id, cycle_id, system_power, started_at, "NO_VALID_PAPER_INTENTS")
            return _json_safe(payload)

        safety_before = self._safety_counts()
        expiry_summary: dict[str, Any] = {}
        with self._factory.connect() as conn:
            with conn.transaction():
                expiry_summary = self._opportunity_memory.expire_stale_intents_for_connection(conn, limit=limit)
            with conn.transaction():
                intents = _list_created_intents(conn, limit=limit)
                executable, blocked_reasons = self._validate_intents(conn, intents)

        if not executable:
            payload = self._run_payload(
                run_id,
                cycle_id,
                system_power,
                started_at,
                "NO_VALID_PAPER_INTENTS",
                intents_checked=len(intents),
                blocked_intents=len(intents),
                block_reasons=dict(blocked_reasons),
                metadata={"reason": "no executable paper intents", "intent_expiry": expiry_summary},
            )
            self._record_run(payload)
            return _json_safe(payload)

        if not self._governor.can_execute(RuntimeAction.RUN_PAPER_SIMULATION):
            payload = self._run_payload(
                run_id,
                cycle_id,
                system_power,
                started_at,
                "PAPER_BLOCKED_BY_MODE",
                intents_checked=len(intents),
                executable_intents=len(executable),
                blocked_intents=len(executable),
                block_reasons={"PAPER_BLOCKED_BY_MODE": len(executable)},
                metadata={"reason": "StateGovernor blocked RUN_PAPER_SIMULATION"},
            )
            self._record_run(payload)
            return _json_safe(payload)

        orders_created = 0
        fills_created = 0
        positions_created = 0
        duplicate_skipped = 0
        errors: list[str] = []
        execution_results: list[dict[str, Any]] = []

        with self._factory.connect() as conn:
            for item in executable:
                try:
                    with conn.transaction():
                        intent = item["intent"]
                        lineage = _lineage_for_intent(conn, str(intent["paper_intent_id"]))
                        if lineage["orders"] or lineage["fills"] or lineage["positions"]:
                            _mark_intent_consumed(conn, str(intent["paper_intent_id"]), "POSITION_OPENED")
                            duplicate_skipped += 1
                            continue
                        order_created, fill_created, position_created, result = self._execute_intent(
                            conn,
                            intent,
                            item["orderbook"],
                            quantity=item["quantity"],
                            fill_price=item["fill_price"],
                            correlation_id=correlation_id,
                            capital_sizing=item.get("capital_sizing"),
                        )
                    orders_created += int(order_created)
                    fills_created += int(fill_created)
                    positions_created += int(position_created)
                    execution_results.append(result)
                except Exception as exc:
                    errors.append(f"{item.get('intent', {}).get('paper_intent_id', 'unknown')}:{type(exc).__name__}:{exc}")

        safety_after = self._safety_counts()
        payload = self._run_payload(
            run_id,
            cycle_id,
            system_power,
            started_at,
            "DEGRADED" if errors else "OK",
            intents_checked=len(intents),
            executable_intents=len(executable),
            orders_created=orders_created,
            fills_created=fills_created,
            positions_created=positions_created,
            blocked_intents=max(0, len(intents) - len(executable)) + len(errors),
            duplicate_skipped=duplicate_skipped,
            block_reasons=dict(blocked_reasons),
            safety_before=safety_before,
            safety_after=safety_after,
            error_message="; ".join(errors) if errors else None,
            metadata={"execution_results": execution_results, "intent_expiry": expiry_summary},
        )
        self._record_run(payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard()
        with self._factory.connect() as conn:
            latest_run = _latest_run(conn)
            intents_total = _count_table(conn, "paper_intents")
            executable = _count_executable_intents(conn)
            paper_orders = _count_table(conn, "paper_orders")
            paper_fills = _count_table(conn, "paper_fills")
            paper_positions = _count_table(conn, "paper_positions")
            open_positions = _count_open_positions(conn)
            latest_order_at = _max_timestamp(conn, "paper_orders", "created_at")
            latest_fill_at = _max_timestamp(conn, "paper_fills", "created_at")
            latest_position_at = _max_timestamp(conn, "paper_positions", "opened_at")
            top_reasons = _top_block_reasons(conn, limit=limit)
            safety = self._safety_counts()
            exit_ready = _table_exists(conn, "paper_exit_loop_runs") and _table_exists(conn, "paper_position_closes")
            pnl_ready = _table_exists(conn, "paper_daily_pnl")
        status = str((latest_run or {}).get("status") or "NO_VALID_PAPER_INTENTS")
        return {
            "mock_data": False,
            "status": status,
            "latest_run": _json_safe(latest_run) if latest_run else None,
            "paper_intents_total": intents_total,
            "executable_intents": executable,
            "blocked_intents": max(0, intents_total - executable),
            "paper_orders": paper_orders,
            "paper_fills": paper_fills,
            "paper_positions": paper_positions,
            "open_paper_positions": open_positions,
            "latest_paper_order_at": latest_order_at.isoformat() if latest_order_at else None,
            "latest_paper_fill_at": latest_fill_at.isoformat() if latest_fill_at else None,
            "latest_paper_position_at": latest_position_at.isoformat() if latest_position_at else None,
            "last_execution_run_status": status,
            "top_block_reasons": top_reasons,
            "real_orders": 0,
            "real_orders_total": safety["real_orders"],
            "live_orders": safety["live_orders"],
            "real_orders_created": _int((latest_run or {}).get("real_orders_delta")),
            "live_orders_created": _int((latest_run or {}).get("live_orders_delta")),
            "fills_v2_created": _int((latest_run or {}).get("fills_v2_delta")),
            "positions_created": _int((latest_run or {}).get("positions_delta")),
            "no_live_execution": safety["live_orders"] == 0,
            "no_fake_fills": True,
            "paper_exit_loop_ready": exit_ready,
            "pnl_ready": pnl_ready,
            "paper_ready": False,
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _validate_intents(self, conn: Any, intents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
        executable: list[dict[str, Any]] = []
        reasons: Counter[str] = Counter()
        for intent in intents:
            blockers = _intent_blockers(intent)
            lineage = _lineage_for_intent(conn, str(intent["paper_intent_id"]))
            if lineage["orders"] or lineage["fills"] or lineage["positions"]:
                blockers.append("INTENT_ALREADY_EXECUTED")
            quantity = _quantity_from_intent(intent)
            if quantity is None or quantity <= 0:
                blockers.append("MISSING_QUANTITY")
            price_resolution = self._resolve_execution_price(conn, intent)
            orderbook = price_resolution.get("orderbook")
            blockers.extend(str(item).upper() for item in _list(price_resolution.get("blockers")))
            fill_price = price_resolution.get("fill_price")
            intended_price = _decimal_or_none(intent.get("intended_price"))
            if intended_price is None:
                blockers.append("MISSING_INTENDED_PRICE")
            if orderbook is not None and fill_price is None:
                blockers.append("MISSING_EXECUTABLE_PRICE")
            if fill_price is not None and intended_price is not None and fill_price > intended_price + _max_slippage(intent):
                blockers.append("LIMIT_NOT_MARKETABLE")
            if not blockers:
                guard_decision = self._same_market_guard.evaluate(
                    conn,
                    market_id=str(intent.get("market_id")),
                    proposed_side=str(intent.get("side") or "").upper(),
                    proposed_candidate_id=str(intent.get("eligibility_id")) if intent.get("eligibility_id") else None,
                    proposed_intent_id=str(intent.get("paper_intent_id")) if intent.get("paper_intent_id") else None,
                    coordinator_decision_id=intent.get("coordinator_decision_id"),
                    evidence=intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {},
                    metadata={"source_layer": "paper_execution", "paper_intent_id": intent.get("paper_intent_id")},
                    write_decision=True,
                )
                if guard_decision.decision != "ALLOW":
                    blockers.append(guard_decision.blocker_reason or "MISSING_STRATEGIC_RATIONALE")
                    if guard_decision.blocker_reason in {
                        "SAME_MARKET_OPPOSING_SIDE_BLOCK",
                        "SAME_MARKET_OPPOSING_INTENT_BLOCK",
                        "SAME_MARKET_OPEN_OPPOSITE_POSITION_BLOCK",
                        "SAME_MARKET_ACTIVE_OPPOSITE_INTENT_BLOCK",
                        "SAME_MARKET_BATCH_CONFLICT_BLOCK",
                    }:
                        blockers.append("MISSING_STRATEGIC_RATIONALE")
                        if guard_decision.blocker_reason in {"SAME_MARKET_OPEN_OPPOSITE_POSITION_BLOCK", "SAME_MARKET_BATCH_CONFLICT_BLOCK"}:
                            blockers.append("SAME_MARKET_OPPOSING_SIDE_BLOCK")
                        if guard_decision.blocker_reason == "SAME_MARKET_ACTIVE_OPPOSITE_INTENT_BLOCK":
                            blockers.append("SAME_MARKET_OPPOSING_INTENT_BLOCK")
            else:
                guard_decision = None
            if not blockers and _is_paper_runtime_decision_intent(intent):
                governance_decision = _runtime_decision_execution_governance(intent)
                if not bool(governance_decision.get("allow_paper_execution")):
                    blockers.append("PAPER_RUNTIME_DECISION_DENIED")
                    blockers.extend(str(item).upper() for item in _list(governance_decision.get("critical_blockers_json")))
            elif not blockers:
                governance_decision = self._lifecycle_governance.authorize_paper_execution(
                    conn,
                    intent=intent,
                    same_market_guard=guard_decision.to_api_dict() if guard_decision else None,
                    write_decision=True,
                )
                if not bool(governance_decision.get("allow_paper_execution")):
                    blockers.append("LIFECYCLE_GOVERNANCE_DENIED")
                    blockers.append(f"LIFECYCLE_ACTIONABILITY_{governance_decision.get('actionability_class') or 'UNKNOWN'}")
                    blockers.extend(str(item).upper() for item in _list(governance_decision.get("critical_blockers_json")))
            capital_sizing: dict[str, Any] | None = None
            if fill_price is not None and quantity is not None and quantity > 0:
                capital_check = self._paper_capital.precheck_fill(
                    conn,
                    paper_intent_id=str(intent.get("paper_intent_id") or ""),
                    fill_price=fill_price,
                    quantity=quantity,
                    write_block=False,
                )
                if not capital_check.allowed:
                    capital_sizing = self._paper_capital.clamp_quantity_for_fill(
                        conn,
                        paper_intent_id=str(intent.get("paper_intent_id") or ""),
                        fill_price=fill_price,
                        quantity=quantity,
                    )
                    if bool(capital_sizing.get("allowed")) and bool(capital_sizing.get("clamped")):
                        quantity = capital_sizing["quantity"]
                    else:
                        blockers.extend([str(item) for item in capital_sizing.get("blockers") or capital_check.blockers])
            if blockers:
                reasons.update(blockers)
                _record_intent_execution_diagnosis(conn, intent, blockers)
                if "NO_EXECUTABLE_PAPER_PRICE" in blockers:
                    _expire_no_executable_price_intent(conn, intent, blockers)
                continue
            _record_intent_execution_diagnosis(conn, intent, [])
            executable.append(
                {
                    "intent": intent,
                    "orderbook": orderbook,
                    "quantity": quantity,
                    "fill_price": fill_price,
                    "capital_sizing": capital_sizing,
                }
            )
        return executable, reasons

    def _resolve_execution_price(self, conn: Any, intent: dict[str, Any]) -> dict[str, Any]:
        """Resolve an execution price without pretending fallback data is trusted."""

        stored = _orderbook_for_intent(conn, intent)
        if stored is not None:
            return _price_resolution(stored, source="TRUSTED_ORDERBOOK", trusted=True)

        market_id = str(intent.get("market_id") or "").strip() or None
        side = str(intent.get("side") or "").upper()
        token_id = _intent_token_id(intent)
        condition_id = _intent_condition_id(intent)
        runtime_decision_id = _intent_runtime_decision_id(intent) or str(intent.get("eligibility_id") or intent.get("paper_intent_id") or "")
        source_review_id = _intent_source_review_id(intent)
        blockers: list[str] = []
        refresh_result: dict[str, Any] | None = None
        refreshed: dict[str, Any] | None = None

        if market_id and token_id and side in {"YES", "NO"}:
            try:
                refresh_result = self._last_mile_orderbook_refresh.ensure_fresh(
                    conn,
                    decision_id=runtime_decision_id,
                    source_review_id=source_review_id,
                    market_id=market_id,
                    condition_id=condition_id,
                    token_id=token_id,
                    side=side,
                    ttl_seconds=FRESH_ORDERBOOK_SECONDS,
                    rate_limit_seconds=30,
                    force=False,
                )
                refreshed = refresh_result.get("orderbook") if isinstance(refresh_result, dict) else None
            except Exception:
                blockers.append("ORDERBOOK_REFRESH_FAILED")
        if is_fresh_orderbook(refreshed, ttl_seconds=FRESH_ORDERBOOK_SECONDS) and _fill_price(refreshed) is not None:
            return _price_resolution(
                refreshed,
                source="LAST_MILE_TRUSTED_ORDERBOOK",
                trusted=True,
                refresh_result=refresh_result,
            )

        latest = latest_matching_orderbook(conn, market_id=market_id, token_id=token_id, side=side)
        if _fallback_price_allowed(conn, latest):
            return _price_resolution(
                latest,
                source="PAPER_LEARNING_PRICE_FALLBACK",
                trusted=False,
                fallback_source="REGULAR_ORDERBOOK",
                fallback_reason="fresh bounded regular orderbook used for PAPER learning execution",
                refresh_result=refresh_result,
            )

        if refresh_result and refresh_result.get("refresh_error"):
            blockers.append(str(refresh_result.get("refresh_error") or "ORDERBOOK_REFRESH_FAILED").upper())
        if not blockers and (market_id and token_id and side in {"YES", "NO"}):
            blockers.append("ORDERBOOK_REFRESH_FAILED")
        blockers.append("NO_EXECUTABLE_PAPER_PRICE")
        return {
            "orderbook": None,
            "fill_price": None,
            "blockers": sorted(set(blockers)),
            "price_metadata": {
                "execution_price_source": "NONE",
                "trusted_orderbook_used": False,
                "fallback_source": "NONE",
                "fallback_reason": "no fresh trusted orderbook or bounded PAPER learning fallback price was available",
                "fallback_learning_only": False,
                "price_confidence": "NONE",
                "orderbook_refresh_state": refresh_result.get("refresh_state") if isinstance(refresh_result, dict) else None,
                "orderbook_refresh_error": refresh_result.get("refresh_error") if isinstance(refresh_result, dict) else None,
            },
        }

    def _execute_intent(
        self,
        conn: Any,
        intent: dict[str, Any],
        orderbook: dict[str, Any],
        *,
        quantity: Decimal,
        fill_price: Decimal,
        correlation_id: str | None,
        capital_sizing: dict[str, Any] | None = None,
    ) -> tuple[bool, bool, bool, dict[str, Any]]:
        now = datetime.now(UTC)
        intent_id = str(intent["paper_intent_id"])
        paper_run_id = _stable_uuid("paper-run", intent_id)
        paper_signal_id = _stable_uuid("paper-signal", intent_id)
        paper_order_id = _stable_uuid("paper-order", intent_id)
        paper_position_id = _stable_uuid("paper-position", intent_id)
        paper_fill_id = f"paper_fill_{_stable_uuid('paper-fill', intent_id).hex}"
        market_id = str(intent["market_id"])
        side = str(intent["side"]).upper()
        paper_session_id = active_paper_session_id(conn) or "NO_ACTIVE_PAPER_SESSION"
        intended_price = _decimal_or_none(intent.get("intended_price")) or fill_price
        notional = quantity * fill_price
        cycle_uuid = _uuid_or_none(correlation_id)
        price_metadata = orderbook.get("_execution_price_metadata") if isinstance(orderbook.get("_execution_price_metadata"), dict) else {}
        price_basis = (
            "ORDERBOOK_BEST_ASK"
            if orderbook.get("best_ask") is not None
            else "ORDERBOOK_MID"
            if orderbook.get("mid_price") is not None
            else str(price_metadata.get("fallback_source") or "UNKNOWN_PRICE_SOURCE")
        )
        metadata = {
            "source_intent_id": intent_id,
            "eligibility_id": intent.get("eligibility_id"),
            "risk_decision_id": intent.get("risk_decision_id"),
            "exit_plan_id": intent.get("exit_plan_id"),
            "orderbook_snapshot_id": orderbook.get("id"),
            "price_basis": price_basis,
            "execution_price_source": price_metadata.get("execution_price_source") or "TRUSTED_ORDERBOOK",
            "trusted_orderbook_used": bool(price_metadata.get("trusted_orderbook_used", True)),
            "fallback_source": price_metadata.get("fallback_source") or "NONE",
            "fallback_reason": price_metadata.get("fallback_reason"),
            "price_confidence": price_metadata.get("price_confidence") or "HIGH",
            "fallback_learning_only": bool(price_metadata.get("fallback_learning_only", False)),
            "price_age_seconds": price_metadata.get("price_age_seconds"),
            "spread": price_metadata.get("spread"),
            "slippage_model": price_metadata.get("slippage_model") or "BEST_ASK_OR_MID_WITH_LIMIT_CHECK",
            "orderbook_source": price_metadata.get("orderbook_source") or orderbook.get("source"),
            "orderbook_refresh_state": price_metadata.get("orderbook_refresh_state"),
            "orderbook_refresh_error": price_metadata.get("orderbook_refresh_error"),
            "risk_capital_clamped": bool((capital_sizing or {}).get("clamped")),
            "risk_capital_clamp_reason": (capital_sizing or {}).get("clamp_reason"),
            "requested_quantity": str((capital_sizing or {}).get("requested_quantity")) if (capital_sizing or {}).get("requested_quantity") is not None else None,
            "requested_notional": str((capital_sizing or {}).get("requested_notional")) if (capital_sizing or {}).get("requested_notional") is not None else None,
            "clamped_quantity": str(quantity) if bool((capital_sizing or {}).get("clamped")) else None,
            "clamped_notional": str(notional) if bool((capital_sizing or {}).get("clamped")) else None,
            "allowed_notional": str((capital_sizing or {}).get("allowed_notional")) if (capital_sizing or {}).get("allowed_notional") is not None else None,
            "risk_capital_original_blockers": (capital_sizing or {}).get("original_blockers") or [],
            "simulated": True,
            "paper_only": True,
            "live": False,
            "correlation_id": correlation_id,
            "paper_session_id": paper_session_id,
        }
        capital_check = self._paper_capital.precheck_fill(
            conn,
            paper_intent_id=intent_id,
            fill_price=fill_price,
            quantity=quantity,
            write_block=True,
        )
        if not capital_check.allowed:
            raise RuntimeError(f"capital guard blocked intent: {','.join(capital_check.blockers)}")
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, cycle_id, mode, started_at, ended_at, status,
                markets_seen_count, markets_ranked_count, candidates_selected_count,
                signals_emitted_count, metadata_json, paper_session_id
            )
            VALUES (%s, %s, 'PAPER_SIM', %s, %s, 'COMPLETED', 1, 1, 1, 1, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                ended_at = EXCLUDED.ended_at,
                status = EXCLUDED.status,
                metadata_json = EXCLUDED.metadata_json,
                paper_session_id = COALESCE(paper_runs.paper_session_id, EXCLUDED.paper_session_id),
                updated_at = now()
            """,
            (paper_run_id, cycle_uuid, now, now, Jsonb(_json_safe(metadata)), paper_session_id),
        )
        conn.execute(
            """
            INSERT INTO paper_signals (
                id, paper_run_id, cycle_id, market_id, decision_id, signal_type,
                intended_outcome, trade_type, bucket_type, confidence,
                expected_edge_proxy, intended_price, intended_size, guard_result,
                reason_code, reason_text, payload_json, paper_session_id
            )
            VALUES (
                %s, %s, %s, %s, NULL, 'WOULD_ENTER',
                %s, 'PAPER_ENTRY', 'PAPER_INTENT', %s,
                NULL, %s, %s, 'PASS',
                'paper_intent_executable', 'paper intent passed safe paper execution validation', %s, %s
            )
            ON CONFLICT (id) DO UPDATE SET
                intended_price = EXCLUDED.intended_price,
                intended_size = EXCLUDED.intended_size,
                payload_json = EXCLUDED.payload_json,
                paper_session_id = COALESCE(paper_signals.paper_session_id, EXCLUDED.paper_session_id)
            """,
            (
                paper_signal_id,
                paper_run_id,
                cycle_uuid,
                market_id,
                side,
                intent.get("confidence"),
                intended_price,
                quantity,
                Jsonb(_json_safe(metadata)),
                paper_session_id,
            ),
        )
        order_created = _not_exists(conn, "paper_orders", "id", paper_order_id)
        conn.execute(
            """
            INSERT INTO paper_orders (
                id, paper_run_id, paper_signal_id, cycle_id, market_id,
                intended_outcome, action, intended_price, intended_size,
                notional, status, fill_ratio, filled_size, remaining_size,
                avg_fill_price, min_size_check_passed, stale_at, payload_json,
                paper_session_id
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, 'BUY', %s, %s,
                %s, 'FILLED', 1, %s, 0,
                %s, true, NULL, %s, %s
            )
            ON CONFLICT (id) DO UPDATE SET
                status = 'FILLED',
                fill_ratio = 1,
                filled_size = EXCLUDED.filled_size,
                remaining_size = 0,
                avg_fill_price = EXCLUDED.avg_fill_price,
                payload_json = EXCLUDED.payload_json,
                paper_session_id = COALESCE(paper_orders.paper_session_id, EXCLUDED.paper_session_id),
                updated_at = now()
            """,
            (
                paper_order_id,
                paper_run_id,
                paper_signal_id,
                cycle_uuid,
                market_id,
                side,
                intended_price,
                quantity,
                notional,
                quantity,
                fill_price,
                Jsonb(_json_safe(metadata)),
                paper_session_id,
            ),
        )
        _append_order_event(conn, paper_order_id, now, metadata)
        fill_created = _not_exists(conn, "paper_fills", "paper_fill_id", paper_fill_id)
        conn.execute(
            """
            INSERT INTO paper_fills (
                paper_fill_id, paper_order_id, source_intent_id, market_id,
                side, fill_price, quantity, price_basis, orderbook_snapshot_id,
                slippage_estimate, correlation_id, metadata_json, paper_session_id, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (paper_fill_id) DO NOTHING
            """,
            (
                paper_fill_id,
                paper_order_id,
                intent_id,
                market_id,
                side,
                fill_price,
                quantity,
                price_basis,
                orderbook.get("id"),
                max(Decimal("0"), fill_price - intended_price),
                correlation_id,
                Jsonb(_json_safe(metadata)),
                paper_session_id,
                now,
            ),
        )
        position_created = _not_exists(conn, "paper_positions", "id", paper_position_id)
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size,
                avg_entry, mark_price, unrealized, realized, current_status,
                thesis_state, invalidation_state, opened_at, updated_at,
                closed_at, payload_json, paper_session_id
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, 0, 0, 'OPEN',
                'ACTIVE', 'NONE', %s, %s,
                NULL, %s, %s
            )
            ON CONFLICT (id) DO NOTHING
            """,
            (
                paper_position_id,
                paper_run_id,
                market_id,
                side,
                quantity,
                fill_price,
                fill_price,
                now,
                now,
                Jsonb(_json_safe({**metadata, "paper_fill_id": paper_fill_id, "paper_order_id": paper_order_id})),
                paper_session_id,
            ),
        )
        conn.execute("UPDATE paper_intents SET paper_session_id=COALESCE(paper_session_id,%s) WHERE paper_intent_id=%s", (paper_session_id, intent_id))
        _append_position_event(conn, paper_position_id, now, {**metadata, "paper_fill_id": paper_fill_id})
        _upsert_open_ledger(conn, paper_position_id, market_id, side, notional, correlation_id, metadata)
        self._paper_capital.lock_on_fill(
            conn,
            paper_intent_id=intent_id,
            paper_order_id=str(paper_order_id),
            paper_fill_id=paper_fill_id,
            paper_position_id=str(paper_position_id),
            fill_price=fill_price,
            quantity=quantity,
            skip_precheck=True,
        )
        self._payout_odds.evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=str(paper_position_id))
        _mark_intent_consumed(conn, intent_id, "POSITION_OPENED")
        return (
            order_created,
            fill_created,
            position_created,
            {
                "paper_intent_id": intent_id,
                "paper_order_id": str(paper_order_id),
                "paper_fill_id": paper_fill_id,
                "paper_position_id": str(paper_position_id),
                "fill_price": float(fill_price),
                "quantity": float(quantity),
                "execution_price_source": metadata["execution_price_source"],
                "trusted_orderbook_used": metadata["trusted_orderbook_used"],
                "fallback_source": metadata["fallback_source"],
                "risk_capital_clamped": metadata["risk_capital_clamped"],
            },
        )

    def _safety_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {"real_orders": 0, "live_orders": 0, "fills_v2": 0, "positions": 0}
        with self._factory.connect() as conn:
            return {
                "real_orders": _count_table(conn, "orders_v2"),
                "live_orders": _count_table(conn, "live_orders"),
                "fills_v2": _count_table(conn, "fills_v2"),
                "positions": _count_table(conn, "positions"),
            }

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            conn.execute(
                """
                INSERT INTO paper_execution_runs (
                    run_id, cycle_id, system_power, started_at, finished_at,
                    status, intents_checked, executable_intents, orders_created,
                    fills_created, positions_created, blocked_intents,
                    duplicate_skipped, block_reasons_json, real_orders_delta,
                    live_orders_delta, fills_v2_delta, positions_delta,
                    error_message, metadata_json, created_at
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(system_power)s, %(started_at)s,
                    %(finished_at)s, %(status)s, %(intents_checked)s,
                    %(executable_intents)s, %(orders_created)s,
                    %(fills_created)s, %(positions_created)s,
                    %(blocked_intents)s, %(duplicate_skipped)s,
                    %(block_reasons_json)s, %(real_orders_delta)s,
                    %(live_orders_delta)s, %(fills_v2_delta)s,
                    %(positions_delta)s, %(error_message)s, %(metadata_json)s,
                    now()
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                {**payload, "block_reasons_json": Jsonb(payload.get("block_reasons_json") or {}), "metadata_json": Jsonb(_json_safe(payload.get("metadata_json") or {}))},
            )

    def _run_payload(
        self,
        run_id: str,
        cycle_id: str | None,
        system_power: str,
        started_at: datetime,
        status: str,
        *,
        intents_checked: int = 0,
        executable_intents: int = 0,
        orders_created: int = 0,
        fills_created: int = 0,
        positions_created: int = 0,
        blocked_intents: int = 0,
        duplicate_skipped: int = 0,
        block_reasons: dict[str, int] | None = None,
        safety_before: dict[str, int] | None = None,
        safety_after: dict[str, int] | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safety_before = safety_before or {"real_orders": 0, "live_orders": 0, "fills_v2": 0, "positions": 0}
        safety_after = safety_after or safety_before
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": status,
            "intents_checked": intents_checked,
            "executable_intents": executable_intents,
            "orders_created": orders_created,
            "fills_created": fills_created,
            "positions_created": positions_created,
            "blocked_intents": blocked_intents,
            "duplicate_skipped": duplicate_skipped,
            "block_reasons_json": block_reasons or {},
            "real_orders_delta": max(0, safety_after.get("real_orders", 0) - safety_before.get("real_orders", 0)),
            "live_orders_delta": max(0, safety_after.get("live_orders", 0) - safety_before.get("live_orders", 0)),
            "fills_v2_delta": max(0, safety_after.get("fills_v2", 0) - safety_before.get("fills_v2", 0)),
            "positions_delta": max(0, safety_after.get("positions", 0) - safety_before.get("positions", 0)),
            "error_message": error_message,
            "metadata_json": metadata or {},
        }


def _list_created_intents(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_intents"):
        return []
    active_session = active_paper_session_id(conn)
    session_clause = (
        "AND (%s::text IS NULL OR paper_session_id = %s::text)"
        if _column_exists(conn, "paper_intents", "paper_session_id")
        else "AND %s::text IS NULL AND %s::text IS NULL"
    )
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT *
            FROM paper_intents
            WHERE intent_status = 'CREATED'
              AND intent_type = 'PAPER_ENTRY_INTENT'
              AND paper_only = true
              AND live = false
              AND execution_allowed = false
              AND order_intent_created = false
              AND COALESCE(is_dry_run_generated, false) = false
              {session_clause}
            ORDER BY created_at ASC, id ASC
            LIMIT %s
            """,
            (active_session, active_session, limit),
        ).fetchall()
    ]


def _intent_blockers(intent: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for key, code in {
        "paper_intent_id": "MISSING_INTENT_ID",
        "market_id": "MISSING_MARKET_ID",
        "side": "MISSING_SIDE",
        "risk_decision_id": "MISSING_RISK_DECISION",
        "exit_plan_id": "MISSING_EXIT_PLAN",
        "eligibility_id": "MISSING_ELIGIBILITY",
    }.items():
        if intent.get(key) in (None, "", []):
            blockers.append(code)
    if not bool(intent.get("paper_only")):
        blockers.append("NOT_PAPER_ONLY")
    if bool(intent.get("live")):
        blockers.append("LIVE_INTENT_BLOCKED")
    if bool(intent.get("execution_allowed")):
        blockers.append("EXECUTION_ALLOWED_UNEXPECTED")
    if bool(intent.get("order_intent_created")):
        blockers.append("ORDER_INTENT_ALREADY_CREATED")
    if bool(intent.get("is_dry_run_generated")):
        blockers.append("DRY_RUN_EVIDENCE")
    updated_at = intent.get("updated_at") or intent.get("created_at")
    if _is_stale_timestamp(updated_at, seconds=600):
        blockers.append("STALE_PAPER_INTENT")
        blockers.append("REFRESH_REQUIRED_BEFORE_EXECUTION")
    raw_blockers = _list(intent.get("blockers"))
    if raw_blockers:
        blockers.extend(f"INTENT_BLOCKER_{str(item).upper()}" for item in raw_blockers)
    side = str(intent.get("side") or "").upper()
    if side not in {"YES", "NO"}:
        blockers.append("INVALID_SIDE")
    return blockers


def _is_paper_runtime_decision_intent(intent: dict[str, Any]) -> bool:
    evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
    if evidence.get("paper_runtime_decision_id"):
        return True
    runtime_decision = evidence.get("paper_runtime_decision")
    return isinstance(runtime_decision, dict) and bool(runtime_decision.get("decision_id"))


def _runtime_decision_execution_governance(intent: dict[str, Any]) -> dict[str, Any]:
    evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
    runtime_decision = evidence.get("paper_runtime_decision") if isinstance(evidence.get("paper_runtime_decision"), dict) else {}
    policy = evidence.get("paper_mode_policy") if isinstance(evidence.get("paper_mode_policy"), dict) else {}
    source_blockers = [
        *_list(runtime_decision.get("blockers_json") if isinstance(runtime_decision, dict) else []),
        *_list(policy.get("blockers") if isinstance(policy, dict) else []),
    ]
    hard_blockers = sorted({str(item).upper() for item in source_blockers if str(item or "").strip()})
    paper_enter_allowed = bool(evidence.get("paper_runtime_decision_id")) and bool(
        policy.get("paper_enter_allowed")
        or (isinstance(runtime_decision, dict) and runtime_decision.get("paper_enter_allowed"))
    )
    allow = paper_enter_allowed and not hard_blockers
    return {
        "allow_paper_execution": allow,
        "actionability_class": "PAPER_LEARNING_EXECUTION" if allow else "PAPER_RUNTIME_BLOCKED",
        "critical_blockers_json": [] if allow else hard_blockers,
        "warnings_json": _list(policy.get("warnings") if isinstance(policy, dict) else []),
        "policy_source": "paper_runtime_decision",
        "paper_is_execution_adapter_only": True,
        "live_enter_allowed": False,
    }


def _is_stale_timestamp(value: Any, *, seconds: int) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return True
    if not isinstance(value, datetime):
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return datetime.now(UTC) - value.astimezone(UTC) > timedelta(seconds=seconds)


def _orderbook_for_intent(conn: Any, intent: dict[str, Any]) -> dict[str, Any] | None:
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
        (snapshot_id, intent.get("market_id"), datetime.now(UTC) - timedelta(seconds=FRESH_ORDERBOOK_SECONDS)),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    if _fill_price(data) is None:
        return None
    data["_execution_price_metadata"] = _execution_price_metadata(
        data,
        execution_price_source="TRUSTED_ORDERBOOK",
        trusted_orderbook_used=True,
        fallback_source="NONE",
        fallback_reason=None,
        price_confidence="HIGH",
    )
    return data


def _price_resolution(
    orderbook: dict[str, Any] | None,
    *,
    source: str,
    trusted: bool,
    fallback_source: str = "NONE",
    fallback_reason: str | None = None,
    refresh_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fill_price = _fill_price(orderbook)
    confidence = "HIGH" if trusted else "MEDIUM"
    if orderbook is not None:
        orderbook["_execution_price_metadata"] = _execution_price_metadata(
            orderbook,
            execution_price_source=source,
            trusted_orderbook_used=trusted,
            fallback_source=fallback_source,
            fallback_reason=fallback_reason,
            price_confidence=confidence,
            refresh_result=refresh_result,
        )
    return {
        "orderbook": orderbook,
        "fill_price": fill_price,
        "blockers": [] if fill_price is not None else ["MISSING_EXECUTABLE_PRICE"],
        "price_metadata": (orderbook or {}).get("_execution_price_metadata") if orderbook else {},
    }


def _execution_price_metadata(
    orderbook: dict[str, Any],
    *,
    execution_price_source: str,
    trusted_orderbook_used: bool,
    fallback_source: str,
    fallback_reason: str | None,
    price_confidence: str,
    refresh_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "execution_price_source": execution_price_source,
        "trusted_orderbook_used": trusted_orderbook_used,
        "orderbook_snapshot_id": orderbook.get("id"),
        "fallback_source": fallback_source,
        "fallback_reason": fallback_reason,
        "price_confidence": price_confidence,
        "fallback_learning_only": not trusted_orderbook_used,
        "price_age_seconds": orderbook_age_seconds(orderbook),
        "spread": _decimal_or_none(orderbook.get("spread")),
        "slippage_model": "BEST_ASK_OR_MID_WITH_LIMIT_CHECK",
        "orderbook_source": orderbook.get("source"),
        "orderbook_refresh_state": refresh_result.get("refresh_state") if isinstance(refresh_result, dict) else None,
        "orderbook_refresh_error": refresh_result.get("refresh_error") if isinstance(refresh_result, dict) else None,
    }


def _fallback_price_allowed(conn: Any, orderbook: dict[str, Any] | None) -> bool:
    if not is_fresh_orderbook(orderbook, ttl_seconds=FRESH_ORDERBOOK_SECONDS):
        return False
    fill_price = _fill_price(orderbook)
    if fill_price is None or fill_price <= 0 or fill_price >= 1:
        return False
    profile = get_active_profile(conn)
    if profile.defense_level >= 100:
        return False
    spread = _decimal_or_none((orderbook or {}).get("spread"))
    if spread is None:
        return profile.defense_level <= 20
    if profile.defense_level <= 20:
        return spread <= Decimal("0.15")
    if profile.defense_level <= 60:
        return spread <= Decimal("0.05")
    return False


def _fill_price(orderbook: dict[str, Any] | None) -> Decimal | None:
    if not orderbook:
        return None
    return _decimal_or_none(orderbook.get("best_ask")) or _decimal_or_none(orderbook.get("mid_price"))


def _intent_token_id(intent: dict[str, Any]) -> str | None:
    evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
    values = [
        intent.get("token_id"),
        evidence.get("token_id"),
        _nested_get(evidence, "paper_runtime_decision", "token_id"),
        _nested_get(evidence, "source_evidence", "token_id"),
        _nested_get(evidence, "paper_runtime_decision", "source_evidence", "token_id"),
    ]
    for value in values:
        if value not in (None, "", []):
            return str(value)
    return None


def _intent_condition_id(intent: dict[str, Any]) -> str | None:
    evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
    values = [
        intent.get("condition_id"),
        evidence.get("condition_id"),
        _nested_get(evidence, "paper_runtime_decision", "condition_id"),
        _nested_get(evidence, "source_evidence", "condition_id"),
    ]
    for value in values:
        if value not in (None, "", []):
            return str(value)
    return None


def _intent_runtime_decision_id(intent: dict[str, Any]) -> str | None:
    evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
    values = [
        evidence.get("paper_runtime_decision_id"),
        _nested_get(evidence, "paper_runtime_decision", "decision_id"),
        intent.get("runtime_decision_id"),
    ]
    for value in values:
        if value not in (None, "", []):
            return str(value)
    return None


def _intent_source_review_id(intent: dict[str, Any]) -> str | None:
    evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
    values = [
        evidence.get("source_review_id"),
        _nested_get(evidence, "paper_runtime_decision", "source_review_id"),
        _nested_get(evidence, "source_evidence", "source_review_id"),
    ]
    for value in values:
        if value not in (None, "", []):
            return str(value)
    return None


def _nested_get(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _quantity_from_intent(intent: dict[str, Any]) -> Decimal | None:
    evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
    for key in ("quantity", "size", "intended_size", "open_quantity"):
        value = evidence.get(key)
        quantity = _decimal_or_none(value)
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
        return DEFAULT_MAX_SLIPPAGE
    return max(Decimal("0"), value)


def _position_exists_for_intent(conn: Any, intent_id: str) -> bool:
    if not _table_exists(conn, "paper_positions"):
        return False
    row = conn.execute(
        """
        SELECT 1
        FROM paper_positions
        WHERE payload_json->>'source_intent_id' = %s
        LIMIT 1
        """,
        (intent_id,),
    ).fetchone()
    return row is not None


def _lineage_for_intent(conn: Any, intent_id: str) -> dict[str, int]:
    return {
        "orders": _count_where_value(
            conn,
            "paper_orders",
            "payload_json->>'source_intent_id' = %s",
            intent_id,
        ),
        "fills": _count_where_value(conn, "paper_fills", "source_intent_id = %s", intent_id),
        "positions": _count_where_value(
            conn,
            "paper_positions",
            "payload_json->>'source_intent_id' = %s",
            intent_id,
        ),
    }


def _mark_intent_consumed(conn: Any, intent_id: str, status: str) -> None:
    if not _table_exists(conn, "paper_intents"):
        return
    conn.execute(
        """
        UPDATE paper_intents
        SET intent_status = %s,
            executed_at = COALESCE(executed_at, now()),
            consumed_at = COALESCE(consumed_at, now()),
            updated_at = now(),
            execution_block_reason = NULL
        WHERE paper_intent_id = %s
          AND intent_status IN ('CREATED', 'READY', 'EXECUTING', 'EXECUTED', 'POSITION_OPENED')
        """,
        (status, intent_id),
    )


def _record_intent_execution_diagnosis(conn: Any, intent: dict[str, Any], blockers: list[str]) -> None:
    if not _table_exists(conn, "paper_intents") or not intent.get("paper_intent_id"):
        return
    reason = ",".join(sorted({str(item).upper() for item in blockers if str(item or "").strip()})) or None
    columns = _columns(conn, "paper_intents")
    assignments = [
        "execution_block_reason = %s",
        "updated_at = now()",
    ]
    params: list[Any] = [reason]
    if "last_execution_attempt_at" in columns:
        assignments.append("last_execution_attempt_at = now()")
    if "execution_attempt_count" in columns:
        assignments.append("execution_attempt_count = COALESCE(execution_attempt_count,0) + 1")
    params.append(intent["paper_intent_id"])
    conn.execute(
        f"""
        UPDATE paper_intents
        SET {", ".join(assignments)}
        WHERE paper_intent_id = %s
        """,
        tuple(params),
    )


def _expire_no_executable_price_intent(conn: Any, intent: dict[str, Any], blockers: list[str]) -> None:
    if not _table_exists(conn, "paper_intents") or not intent.get("paper_intent_id"):
        return
    columns = _columns(conn, "paper_intents")
    assignments = [
        "intent_status = 'EXPIRED_NO_EXECUTION'",
        "execution_block_reason = %s",
        "updated_at = now()",
    ]
    params: list[Any] = [",".join(sorted({str(item).upper() for item in blockers if str(item or "").strip()}))]
    if "expired_at" in columns:
        assignments.append("expired_at = COALESCE(expired_at, now())")
    if "cancelled_at" in columns:
        assignments.append("cancelled_at = COALESCE(cancelled_at, now())")
    if "cancellation_reason" in columns:
        assignments.append("cancellation_reason = COALESCE(cancellation_reason, 'NO_EXECUTABLE_PAPER_PRICE')")
    params.append(intent["paper_intent_id"])
    conn.execute(
        f"""
        UPDATE paper_intents
        SET {", ".join(assignments)}
        WHERE paper_intent_id = %s
          AND intent_type = 'PAPER_ENTRY_INTENT'
          AND intent_status NOT IN ('POSITION_OPENED', 'EXECUTED', 'FILLED', 'CLOSED', 'RESET_CLOSED', 'RESET_ARCHIVED')
        """,
        tuple(params),
    )


def _count_where_value(conn: Any, table: str, where: str, value: Any) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}", (value,)).fetchone()
    return _int(row["count"] if row else 0)


def _upsert_open_ledger(conn: Any, position_id: UUID, market_id: str, side: str, amount: Decimal, correlation_id: str | None, metadata: dict[str, Any]) -> None:
    if not _table_exists(conn, "paper_trade_ledger"):
        return
    conn.execute(
        """
        INSERT INTO paper_trade_ledger (
            ledger_id, position_id, event_type, market_id, side, amount,
            realized_pnl, unrealized_pnl, reason, correlation_id, metadata_json
        )
        VALUES (%s, %s, 'OPEN', %s, %s, %s, NULL, 0, 'PAPER_POSITION_OPENED', %s, %s)
        ON CONFLICT (ledger_id) DO NOTHING
        """,
        (f"paper_open_{position_id}", position_id, market_id, side, amount, correlation_id, Jsonb(_json_safe(metadata))),
    )


def _append_order_event(conn: Any, paper_order_id: UUID, now: datetime, metadata: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO paper_order_events (
            id, paper_order_id, event_at, old_status, new_status,
            reason_code, reason_text, payload_json
        )
        VALUES (%s, %s, %s, NULL, 'FILLED', 'paper_execution_simulated_fill', 'paper order filled by safe paper execution service', %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (_stable_uuid("paper-order-event", str(paper_order_id)), paper_order_id, now, Jsonb(_json_safe(metadata))),
    )


def _append_position_event(conn: Any, paper_position_id: UUID, now: datetime, metadata: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO paper_position_events (
            id, paper_position_id, event_at, event_type, reason_code,
            reason_text, payload_json
        )
        VALUES (%s, %s, %s, 'OPENED', 'paper_execution_opened_position', 'paper position opened from simulated fill', %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (_stable_uuid("paper-position-event", str(paper_position_id)), paper_position_id, now, Jsonb(_json_safe(metadata))),
    )


def _stable_uuid(prefix: str, value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"polybot:{prefix}:{value}")


def _uuid_or_none(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _not_exists(conn: Any, table: str, column: str, value: Any) -> bool:
    if not _table_exists(conn, table):
        return True
    row = conn.execute(f"SELECT 1 FROM {table} WHERE {column} = %s LIMIT 1", (value,)).fetchone()
    return row is None


def _latest_run(conn: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_execution_runs"):
        return None
    row = conn.execute("SELECT * FROM paper_execution_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _count_executable_intents(conn: Any) -> int:
    if not _table_exists(conn, "paper_intents"):
        return 0
    return _int(
        conn.execute(
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
              AND side IS NOT NULL
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
              AND (
                  evidence ? 'quantity'
                  OR evidence ? 'size'
                  OR evidence ? 'intended_size'
                  OR evidence ? 'open_quantity'
                  OR evidence ? 'notional'
                  OR evidence ? 'intended_notional'
              )
            """
        ).fetchone()["count"]
    )


def _top_block_reasons(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_execution_runs"):
        return []
    rows = conn.execute(
        """
        SELECT key AS reason, SUM(value::int) AS count
        FROM paper_execution_runs, jsonb_each_text(block_reasons_json)
        GROUP BY key
        ORDER BY count DESC, reason ASC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _max_timestamp(conn: Any, table: str, column: str) -> datetime | None:
    if not _table_exists(conn, table):
        return None
    row = conn.execute(f"SELECT MAX({column}) AS ts FROM {table}").fetchone()
    return row["ts"] if row else None


def _count_open_positions(conn: Any) -> int:
    if not _table_exists(conn, "paper_positions"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM paper_positions
        WHERE current_status = 'OPEN'
          AND closed_at IS NULL
        """
    ).fetchone()
    return _int(row["count"] if row else 0)


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return _int(row["count"] if row else 0)


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table_name,)).fetchone()
    return bool(row and row["table_name"])


def _column_exists(conn: Any, table_name: str, column_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = ANY(current_schemas(false))
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name),
    ).fetchone()
    return bool(row)


def _columns(conn: Any, table_name: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = ANY(current_schemas(false))
          AND table_name = %s
        """,
        (table_name,),
    ).fetchall()
    return {str(row["column_name"]) for row in rows}


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


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _empty_dashboard() -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": "NO_VALID_PAPER_INTENTS",
        "latest_run": None,
        "paper_intents_total": 0,
        "executable_intents": 0,
        "blocked_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "open_paper_positions": 0,
        "latest_paper_order_at": None,
        "latest_paper_fill_at": None,
        "latest_paper_position_at": None,
        "last_execution_run_status": "NO_VALID_PAPER_INTENTS",
        "top_block_reasons": [],
        "real_orders": 0,
        "live_orders": 0,
        "real_orders_created": 0,
        "live_orders_created": 0,
        "fills_v2_created": 0,
        "positions_created": 0,
        "no_live_execution": True,
        "no_fake_fills": True,
        "paper_exit_loop_ready": False,
        "pnl_ready": False,
        "paper_ready": False,
        "last_updated": datetime.now(UTC).isoformat(),
    }
