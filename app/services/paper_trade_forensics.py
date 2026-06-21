from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.services.capital_efficiency import CapitalEfficiencyService
from app.services.exit_hold_reasoning import ExitHoldReasoningService
from app.services.lifecycle_governance import LifecycleGovernanceGateService
from app.services.payout_odds import PayoutOddsService
from app.services.risk_evidence_mesh import RiskEvidenceMeshService
from app.services.trade_lifecycle import TradeLifecycleService
from app.services.truth_state import TruthStateService


class PaperTradeForensicsService:
    """Read-only lineage and decision trace for canonical paper positions."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def list_trades(self, *, limit: int = 100) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return {
                "mock_data": False,
                "status": "DATABASE_UNAVAILABLE",
                "generated_at": generated_at,
                "active_trades": [],
                "legacy_quarantined": [],
                "missing_links": [],
            }
        with self._factory.connect() as conn:
            rows = _fetchall(
                conn,
                """
                SELECT *
                FROM paper_positions
                ORDER BY opened_at DESC NULLS LAST, updated_at DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (limit,),
            )
            traces = [self._trace_from_position(conn, row, compact=True) for row in rows]
        active = [item for item in traces if item.get("quarantine_status", {}).get("status") != "LEGACY_QUARANTINED"]
        quarantined = [item for item in traces if item.get("quarantine_status", {}).get("status") == "LEGACY_QUARANTINED"]
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "count": len(traces),
                "active_count": len(active),
                "legacy_quarantined_count": len(quarantined),
                "active_trades": active,
                "legacy_quarantined": quarantined,
                "pnl_summary": {
                    "realized_pnl": sum(Decimal(str(item.get("realized_pnl") or 0)) for item in active),
                    "unrealized_pnl": sum(Decimal(str(item.get("unrealized_pnl") or 0)) for item in active),
                },
                "missing_links": [link for item in traces for link in item.get("missing_links", [])],
            }
        )

    def get_trade(self, paper_position_id: str) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "generated_at": generated_at}
        with self._factory.connect() as conn:
            row = _fetchone(conn, "SELECT * FROM paper_positions WHERE id::text = %s", (paper_position_id,))
            if row is None:
                return {"mock_data": False, "status": "NOT_FOUND", "generated_at": generated_at}
            trace = self._trace_from_position(conn, row, compact=False)
        trace["mock_data"] = False
        trace["response_status"] = "OK"
        trace["generated_at"] = generated_at
        return _json_safe(trace)

    def _trace_from_position(self, conn: Any, position: dict[str, Any], *, compact: bool) -> dict[str, Any]:
        payload = _dict(position.get("payload_json"))
        position_id = str(position.get("id"))
        paper_fill_id = _text(payload.get("paper_fill_id"))
        fill = _fetchone(conn, "SELECT * FROM paper_fills WHERE paper_fill_id = %s", (paper_fill_id,)) if paper_fill_id else None
        if fill and not paper_fill_id:
            paper_fill_id = _text(fill.get("paper_fill_id"))
        paper_order_id = _text(payload.get("paper_order_id")) or _text((fill or {}).get("paper_order_id"))
        order = _fetchone(conn, "SELECT * FROM paper_orders WHERE id::text = %s", (paper_order_id,)) if paper_order_id else None
        paper_intent_id = _text(payload.get("source_intent_id")) or _text((fill or {}).get("source_intent_id")) or _text(_dict((order or {}).get("payload_json")).get("source_intent_id"))
        intent = _fetchone(conn, "SELECT * FROM paper_intents WHERE paper_intent_id = %s", (paper_intent_id,)) if paper_intent_id else None
        eligibility_id = _text(payload.get("eligibility_id")) or _text((intent or {}).get("eligibility_id"))
        eligibility = _fetchone(conn, "SELECT * FROM paper_eligibility_candidates WHERE eligibility_id = %s", (eligibility_id,)) if eligibility_id else None
        risk_decision_id = _text(payload.get("risk_decision_id")) or _text((intent or {}).get("risk_decision_id")) or _text((eligibility or {}).get("risk_decision_id"))
        exit_plan_id = _text(payload.get("exit_plan_id")) or _text((intent or {}).get("exit_plan_id")) or _text((eligibility or {}).get("exit_plan_id"))
        risk = _fetch_optional_by_text_id(conn, "risk_decisions", "risk_decision_id", risk_decision_id)
        exit_plan = _fetch_optional_by_text_id(conn, "exit_plans", "exit_plan_id", exit_plan_id)
        close = _fetchone(conn, "SELECT * FROM paper_position_closes WHERE position_id::text = %s", (position_id,))
        ledger_rows = _fetchall(conn, "SELECT * FROM paper_trade_ledger WHERE position_id::text = %s ORDER BY created_at ASC, id ASC", (position_id,))
        capital_rows = self._capital_ledger(conn, position_id, paper_intent_id, paper_order_id, paper_fill_id, _text((close or {}).get("close_id")))
        capital_lineage = self._capital_lineage(position, capital_rows)
        guard_decisions = self._same_market_guard_decisions(conn, position.get("market_id"), position.get("intended_outcome"), paper_intent_id, eligibility_id)
        payout_odds = PayoutOddsService(connection_factory=self._factory).latest_for_subject(conn, subject_type="PAPER_POSITION", subject_id=position_id)
        exit_hold = ExitHoldReasoningService(connection_factory=self._factory).latest_for_subject(conn, subject_type="PAPER_POSITION", subject_id=position_id)
        capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).latest_for_subject(conn, subject_type="PAPER_POSITION", subject_id=position_id)
        trade_lifecycle = TradeLifecycleService(connection_factory=self._factory).latest_for_subject(conn, subject_type="PAPER_POSITION", subject_id=position_id)
        lifecycle_governance = LifecycleGovernanceGateService(connection_factory=self._factory).latest_for_subject(conn, subject_type="PAPER_POSITION", subject_id=position_id)
        risk_evidence_mesh = RiskEvidenceMeshService(connection_factory=self._factory).latest_for_subject(conn, subject_type="PAPER_POSITION", subject_id=position_id)
        truth_state = TruthStateService(connection_factory=self._factory).subject_detail(position_id, limit=50) if _table_exists(conn, "truth_state_registry") else {"truth_records": []}
        lifecycle_sources = _fetchall(conn, "SELECT * FROM trade_lifecycle_plan_sources WHERE plan_id=%s ORDER BY linked_at,id", (trade_lifecycle["plan_id"],)) if trade_lifecycle and _table_exists(conn, "trade_lifecycle_plan_sources") else []
        lifecycle_contributions = _fetchall(conn, "SELECT * FROM trade_lifecycle_brain_contributions WHERE plan_id=%s ORDER BY created_at,id", (trade_lifecycle["plan_id"],)) if trade_lifecycle and _table_exists(conn, "trade_lifecycle_brain_contributions") else []
        freshness_checks = _fetchall(
            conn,
            """
            SELECT *
            FROM freshness_governance_checks
            WHERE subject_type='PAPER_POSITION' AND subject_id=%s
            ORDER BY created_at DESC,id DESC
            LIMIT 50
            """,
            (position_id,),
        ) if _table_exists(conn, "freshness_governance_checks") else []
        orderbook_id = _text((fill or {}).get("orderbook_snapshot_id")) or _text((intent or {}).get("orderbook_snapshot_id")) or _text(payload.get("orderbook_snapshot_id"))
        orderbook = _fetchone(conn, "SELECT * FROM orderbook_snapshots WHERE id::text = %s OR orderbook_snapshot_id = %s", (orderbook_id, orderbook_id)) if orderbook_id else None
        session = self._session(conn, position)
        session_id = _text((session or {}).get("session_id"))
        awareness = _fetchone(conn, "SELECT * FROM mesh_shared_awareness WHERE session_id = %s", (session_id,)) if session_id else None
        opinions = _fetchall(conn, "SELECT * FROM mesh_brain_opinions WHERE session_id = %s ORDER BY created_at ASC, id ASC", (session_id,)) if session_id else []
        coordinator = _fetchone(conn, "SELECT * FROM mesh_coordinator_decisions WHERE session_id = %s ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,)) if session_id else None
        capital_eval = _fetchone(conn, "SELECT * FROM capital_brain_evaluations WHERE session_id = %s ORDER BY created_at DESC, id DESC LIMIT 1", (session_id,)) if session_id else None
        dialogue = self._dialogue(conn, position_id, paper_intent_id, paper_order_id, paper_fill_id, position.get("market_id"))
        source_events = self._source_events(conn, position_id, position.get("market_id"), session_id)
        quarantine = self._quarantine(conn, position)
        missing_links = self._missing_links(
            paper_position_id=position_id,
            paper_fill_id=paper_fill_id,
            paper_order_id=paper_order_id,
            paper_intent_id=paper_intent_id,
            eligibility_id=eligibility_id,
            risk_decision_id=risk_decision_id,
            exit_plan_id=exit_plan_id,
            orderbook_id=orderbook_id,
            fill=fill,
            order=order,
            intent=intent,
            eligibility=eligibility,
            risk=risk,
            exit_plan=exit_plan,
            orderbook=orderbook,
            close=close,
            position=position,
        )
        trace: dict[str, Any] = {
            "paper_position_id": position_id,
            "market_id": position.get("market_id"),
            "side": position.get("intended_outcome"),
            "entry_price": position.get("avg_entry"),
            "quantity": position.get("size"),
            "opened_at": position.get("opened_at"),
            "closed_at": position.get("closed_at"),
            "status": position.get("current_status"),
            "paper_intent_id": paper_intent_id,
            "paper_order_id": paper_order_id,
            "paper_fill_id": paper_fill_id,
            "risk_decision_id": risk_decision_id,
            "exit_plan_id": exit_plan_id,
            "eligibility_id": eligibility_id,
            "capital_evaluation_id": (capital_eval or {}).get("evaluation_id"),
            "coordinator_decision_id": (coordinator or {}).get("decision_id") or (intent or {}).get("coordinator_decision_id"),
            "entry_reason": (intent or {}).get("intent_reason") or payload.get("entry_reason"),
            "exit_reason": (close or {}).get("exit_reason"),
            "exit_trigger": _dict((close or {}).get("metadata_json")).get("exit_trigger") or (close or {}).get("exit_reason"),
            "exit_price": (close or {}).get("exit_price"),
            "realized_pnl": (close or {}).get("realized_pnl") if close else position.get("realized"),
            "unrealized_pnl": position.get("unrealized"),
            "capital_lock_row": capital_lineage["capital_lock_row"],
            "capital_release_row": capital_lineage["capital_release_row"],
            "active_capital_lock": capital_lineage["active_capital_lock"],
            "expected_exposure": capital_lineage["expected_exposure"],
            "capital_reconciliation_status": capital_lineage["capital_reconciliation_status"],
            "same_market_guard_decision": guard_decisions[0] if guard_decisions else None,
            "same_market_guard_decisions": guard_decisions,
            "same_market_guard_status": guard_decisions[0]["decision"] if guard_decisions else "NO_GUARD_DECISION_RECORDED",
            "payout_odds_evaluation": payout_odds,
            "implied_probability_at_entry": (payout_odds or {}).get("implied_probability"),
            "stake": (payout_odds or {}).get("stake_usd"),
            "cost_basis": (payout_odds or {}).get("stake_usd"),
            "shares": (payout_odds or {}).get("quantity"),
            "payout_if_win": (payout_odds or {}).get("payout_if_win"),
            "profit_if_win": (payout_odds or {}).get("profit_if_win"),
            "max_loss": (payout_odds or {}).get("max_loss"),
            "risk_reward": (payout_odds or {}).get("risk_reward"),
            "break_even_probability": (payout_odds or {}).get("break_even_probability"),
            "current_exit_value": _dict((payout_odds or {}).get("metadata_json")).get("current_exit_value"),
            "missing_payout_fields": _missing_payout_fields(payout_odds),
            "exit_hold_evaluation": exit_hold,
            "exit_now_value": (exit_hold or {}).get("exit_now_value"),
            "exit_now_pnl": (exit_hold or {}).get("exit_now_pnl"),
            "hold_to_resolution_value": (exit_hold or {}).get("hold_to_resolution_value"),
            "hold_to_resolution_profit_if_win": (exit_hold or {}).get("hold_to_resolution_profit_if_win"),
            "time_to_resolution": (exit_hold or {}).get("time_to_resolution_seconds"),
            "exit_hold_decision": (exit_hold or {}).get("decision"),
            "exit_hold_reason": (exit_hold or {}).get("reason"),
            "exit_hold_missing_inputs": (exit_hold or {}).get("missing_inputs_json") if exit_hold else ["EXIT_HOLD_EVALUATION_MISSING"],
            "capital_efficiency_evaluation": capital_efficiency,
            "capital_locked": (capital_efficiency or {}).get("capital_locked"),
            "time_locked": (capital_efficiency or {}).get("time_locked_seconds"),
            "capital_efficiency_time_to_resolution": (capital_efficiency or {}).get("time_to_resolution_seconds"),
            "reward_per_dollar_hour": (capital_efficiency or {}).get("reward_per_dollar_hour"),
            "capital_efficiency_score": (capital_efficiency or {}).get("capital_efficiency_score"),
            "capital_allocation_recommendation": (capital_efficiency or {}).get("recommendation"),
            "capital_efficiency_missing_inputs": (capital_efficiency or {}).get("missing_inputs_json") if capital_efficiency else ["CAPITAL_EFFICIENCY_EVALUATION_MISSING"],
            "risk_evidence_mesh_evaluation": risk_evidence_mesh,
            "risk_evidence_mesh_decision": (risk_evidence_mesh or {}).get("risk_decision"),
            "risk_evidence_mesh_blocker_subtype": (risk_evidence_mesh or {}).get("risk_blocker_subtype"),
            "risk_evidence_mesh_edge_source_type": (risk_evidence_mesh or {}).get("edge_source_type"),
            "risk_evidence_mesh_critical_evidence_missing": (risk_evidence_mesh or {}).get("critical_evidence_missing_json") if risk_evidence_mesh else ["RISK_EVIDENCE_MESH_MISSING"],
            "risk_evidence_mesh_optional_context_missing": (risk_evidence_mesh or {}).get("optional_context_missing_json") if risk_evidence_mesh else [],
            "trade_lifecycle_plan": trade_lifecycle,
            "lifecycle_strategy_type": (trade_lifecycle or {}).get("strategy_type"),
            "lifecycle_plan_status": (trade_lifecycle or {}).get("plan_status"),
            "lifecycle_decision_class": (trade_lifecycle or {}).get("decision_class"),
            "lifecycle_economic_thesis": (trade_lifecycle or {}).get("economic_thesis"),
            "lifecycle_entry_thesis": (trade_lifecycle or {}).get("entry_thesis"),
            "lifecycle_exit_thesis": (trade_lifecycle or {}).get("exit_thesis"),
            "lifecycle_hold_to_resolution_thesis": (trade_lifecycle or {}).get("hold_to_resolution_thesis"),
            "lifecycle_capital_plan": (trade_lifecycle or {}).get("capital_plan_json"),
            "lifecycle_monitoring_plan": (trade_lifecycle or {}).get("monitoring_plan_json"),
            "lifecycle_invalidation_rules": (trade_lifecycle or {}).get("invalidation_rules_json"),
            "lifecycle_coordinator_judgment": (trade_lifecycle or {}).get("coordinator_judgment_json"),
            "lifecycle_missing_inputs": (trade_lifecycle or {}).get("missing_inputs_json") if trade_lifecycle else ["TRADE_LIFECYCLE_PLAN_MISSING"],
            "lifecycle_brain_contributions": lifecycle_contributions,
            "lifecycle_governance_decision": lifecycle_governance,
            "lifecycle_governance_actionability_class": (lifecycle_governance or {}).get("actionability_class"),
            "lifecycle_governance_critical_blockers": (lifecycle_governance or {}).get("critical_blockers_json") if lifecycle_governance else ["LIFECYCLE_GOVERNANCE_MISSING"],
            "lifecycle_governance_optional_missing": (lifecycle_governance or {}).get("optional_missing_json") if lifecycle_governance else [],
            "lifecycle_governance_allows_intent": bool((lifecycle_governance or {}).get("allow_paper_intent")),
            "lifecycle_governance_allows_execution": bool((lifecycle_governance or {}).get("allow_paper_execution")),
            "lifecycle_governance_risk_source_trace": _dict(_dict((lifecycle_governance or {}).get("metadata_json")).get("risk_source_trace")),
            "selected_risk_source": _dict(_dict((lifecycle_governance or {}).get("metadata_json")).get("risk_source_trace")).get("selected_risk_source"),
            "legacy_risk_ignored": bool(_dict(_dict((lifecycle_governance or {}).get("metadata_json")).get("risk_source_trace")).get("legacy_ignored")),
            "freshness_governance_checks": freshness_checks,
            "freshness_status": _freshness_status(freshness_checks),
            "governance_freshness": _freshness_status([row for row in freshness_checks if row.get("source_type") in {"LIFECYCLE_GOVERNANCE", "LIFECYCLE_PLAN"}]),
            "truth_state_records": truth_state.get("truth_records", []),
            "truth_state_summary": _truth_state_summary(truth_state.get("truth_records", [])),
            "blocker_classification": _dict((lifecycle_governance or {}).get("metadata_json")).get("missing_input_classification"),
            "quarantine_status": quarantine,
            "missing_links": missing_links,
        }
        if compact:
            trace["supporting_brain_opinions"] = [_opinion_summary(row) for row in opinions if row.get("stance") == "SUPPORT"]
            trace["opposing_brain_opinions"] = [_opinion_summary(row) for row in opinions if row.get("stance") in {"CAUTION", "BLOCK"}]
            return trace
        trace.update(
            {
                "paper_position": position,
                "paper_fill": fill,
                "paper_order": order,
                "paper_intent": intent,
                "eligibility": eligibility,
                "risk_decision": risk,
                "exit_plan": exit_plan,
                "paper_close": close,
                "supporting_brain_opinions": [_opinion_summary(row) for row in opinions if row.get("stance") == "SUPPORT"],
                "opposing_brain_opinions": [_opinion_summary(row) for row in opinions if row.get("stance") in {"CAUTION", "BLOCK"}],
                "all_brain_opinions": opinions,
                "shared_awareness_snapshot_at_entry": awareness,
                "shared_awareness_snapshot_note": "LATEST_AVAILABLE_FOR_SESSION" if awareness else "MISSING_LINK",
                "mesh_session": session,
                "mesh_coordinator_decision": coordinator,
                "capital_evaluation": capital_eval,
                "orderbook_snapshot_used": orderbook,
                "capital_state_at_entry": self._capital_state_at_entry(capital_rows),
                "capital_lineage": capital_lineage,
                "same_market_guard_lineage": guard_decisions,
                "payout_odds_lineage": payout_odds,
                "exit_hold_lineage": exit_hold,
                "capital_efficiency_lineage": capital_efficiency,
                "risk_evidence_mesh_lineage": risk_evidence_mesh,
                "trade_lifecycle_lineage": {
                    "plan": trade_lifecycle,
                    "sources": lifecycle_sources,
                    "brain_contributions": lifecycle_contributions,
                },
                "lifecycle_governance_lineage": lifecycle_governance,
                "freshness_governance_lineage": freshness_checks,
                "ledger_rows": {"paper_trade_ledger": ledger_rows, "paper_capital_ledger": capital_rows},
                "dialogue_timeline": dialogue,
                "source_events": source_events,
            }
        )
        return trace

    def _capital_ledger(
        self,
        conn: Any,
        position_id: str,
        intent_id: str | None,
        order_id: str | None,
        fill_id: str | None,
        close_id: str | None,
    ) -> list[dict[str, Any]]:
        clauses = ["paper_position_id = %s"]
        params: list[Any] = [position_id]
        for column, value in (
            ("paper_intent_id", intent_id),
            ("paper_order_id", order_id),
            ("paper_fill_id", fill_id),
            ("paper_close_id", close_id),
        ):
            if value:
                clauses.append(f"{column} = %s")
                params.append(value)
        return _fetchall(
            conn,
            f"""
            SELECT *
            FROM paper_capital_ledger
            WHERE {" OR ".join(clauses)}
            ORDER BY created_at ASC, id ASC
            """,
            tuple(params),
        )

    def _capital_state_at_entry(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        for row in rows:
            if row.get("event_type") == "CAPITAL_LOCKED_ON_FILL":
                return {
                    "ledger_id": row.get("ledger_id"),
                    "balance_before": row.get("balance_before"),
                    "balance_after": row.get("balance_after"),
                    "available_before": row.get("available_before"),
                    "available_after": row.get("available_after"),
                    "locked_before": row.get("locked_before"),
                    "locked_after": row.get("locked_after"),
                    "created_at": row.get("created_at"),
                }
        return None

    def _capital_lineage(self, position: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
        lock_rows = [row for row in rows if row.get("event_type") in {"CAPITAL_LOCKED_ON_FILL", "CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL"}]
        release_rows = [row for row in rows if row.get("event_type") in {"CAPITAL_RELEASED_ON_CLOSE", "CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE"}]
        locked = sum((Decimal(str(row.get("amount") or 0)) for row in lock_rows), Decimal("0"))
        released = sum((Decimal(str(row.get("amount") or 0)) for row in release_rows), Decimal("0"))
        active_lock = locked - released
        is_open = position.get("closed_at") is None and position.get("current_status") in {"OPEN", "EXIT_PENDING"}
        expected = Decimal(str(position.get("avg_entry") or 0)) * Decimal(str(position.get("size") or 0)) if is_open else Decimal("0")
        status = "OK"
        if is_open and active_lock <= 0:
            status = "RED"
        elif not is_open and active_lock != 0:
            status = "RED"
        elif len(release_rows) > 1:
            status = "RED"
        return {
            "capital_lock_row": lock_rows[-1] if lock_rows else None,
            "capital_release_row": release_rows[-1] if release_rows else None,
            "lock_event_count": len(lock_rows),
            "release_event_count": len(release_rows),
            "locked_amount": locked,
            "released_amount": released,
            "active_capital_lock": active_lock,
            "expected_exposure": expected,
            "capital_reconciliation_status": status,
        }

    def _same_market_guard_decisions(
        self,
        conn: Any,
        market_id: Any,
        side: Any,
        intent_id: str | None,
        eligibility_id: str | None,
    ) -> list[dict[str, Any]]:
        if not _table_exists(conn, "same_market_side_guard_decisions"):
            return []
        clauses = ["market_id = %s"]
        params: list[Any] = [str(market_id)]
        if side:
            clauses.append("proposed_side = %s")
            params.append(str(side).upper())
        identity_clauses: list[str] = []
        if intent_id:
            identity_clauses.append("proposed_intent_id = %s")
            params.append(intent_id)
        if eligibility_id:
            identity_clauses.append("proposed_candidate_id = %s")
            params.append(eligibility_id)
        where = " AND ".join(clauses)
        if identity_clauses:
            where = f"{where} AND ({' OR '.join(identity_clauses)})"
        params.append(20)
        return _fetchall(
            conn,
            f"""
            SELECT *
            FROM same_market_side_guard_decisions
            WHERE {where}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            tuple(params),
        )

    def _session(self, conn: Any, position: dict[str, Any]) -> dict[str, Any] | None:
        position_id = str(position.get("id"))
        row = _fetchone(
            conn,
            """
            SELECT *
            FROM mesh_sessions
            WHERE position_id = %s
            ORDER BY last_event_at DESC NULLS LAST, opened_at DESC, id DESC
            LIMIT 1
            """,
            (position_id,),
        )
        if row:
            return row
        return _fetchone(
            conn,
            """
            SELECT *
            FROM mesh_sessions
            WHERE market_id = %s
            ORDER BY last_event_at DESC NULLS LAST, opened_at DESC, id DESC
            LIMIT 1
            """,
            (position.get("market_id"),),
        )

    def _dialogue(
        self,
        conn: Any,
        position_id: str,
        intent_id: str | None,
        order_id: str | None,
        fill_id: str | None,
        market_id: Any,
    ) -> list[dict[str, Any]]:
        clauses = ["paper_position_id = %s"]
        params: list[Any] = [position_id]
        for column, value in (("paper_intent_id", intent_id), ("paper_order_id", order_id), ("paper_fill_id", fill_id), ("market_id", market_id)):
            if value:
                clauses.append(f"{column} = %s")
                params.append(value)
        return _fetchall(
            conn,
            f"""
            SELECT *
            FROM brain_dialogue_events
            WHERE {" OR ".join(clauses)}
            ORDER BY timestamp ASC, id ASC
            LIMIT 200
            """,
            tuple(params),
        )

    def _source_events(self, conn: Any, position_id: str, market_id: Any, session_id: str | None) -> list[dict[str, Any]]:
        rows = _fetchall(
            conn,
            """
            SELECT *
            FROM neural_events
            WHERE position_id = %s OR market_id = %s
            ORDER BY created_at ASC, id ASC
            LIMIT 200
            """,
            (position_id, market_id),
        )
        if session_id:
            rows.extend(
                _fetchall(
                    conn,
                    """
                    SELECT ne.*
                    FROM mesh_session_events mse
                    JOIN neural_events ne ON ne.event_id = mse.event_id
                    WHERE mse.session_id = %s
                    ORDER BY ne.created_at ASC, ne.id ASC
                    LIMIT 200
                    """,
                    (session_id,),
                )
            )
        seen = set()
        unique = []
        for row in rows:
            key = row.get("event_id") or row.get("id")
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique[:200]

    def _quarantine(self, conn: Any, position: dict[str, Any]) -> dict[str, Any]:
        position_id = str(position.get("id"))
        audit = _fetchone(conn, "SELECT * FROM paper_lineage_quarantine WHERE entity_type = 'paper_position' AND entity_id = %s", (position_id,))
        quarantined = bool(position.get("excluded_from_active_paper_truth")) or str(position.get("current_status")) == "QUARANTINED"
        return {
            "status": "LEGACY_QUARANTINED" if quarantined else "ACTIVE_TRUTH",
            "consistency_status": position.get("consistency_status"),
            "excluded_from_active_paper_truth": position.get("excluded_from_active_paper_truth"),
            "invalidated_at": position.get("invalidated_at"),
            "quarantine_reason": position.get("quarantine_reason") or (audit or {}).get("reason"),
            "quarantine_source": position.get("quarantine_source"),
            "quarantine_run_id": position.get("quarantine_run_id") or (audit or {}).get("run_id"),
            "quarantine_audit": audit,
        }

    def _missing_links(self, **kwargs: Any) -> list[dict[str, Any]]:
        checks = (
            ("paper_positions", "payload_json.paper_fill_id", kwargs["paper_fill_id"], kwargs["fill"]),
            ("paper_fills", "paper_order_id", kwargs["paper_order_id"], kwargs["order"]),
            ("paper_fills", "source_intent_id", kwargs["paper_intent_id"], kwargs["intent"]),
            ("paper_intents", "eligibility_id", kwargs["eligibility_id"], kwargs["eligibility"]),
            ("paper_intents", "risk_decision_id", kwargs["risk_decision_id"], kwargs["risk"]),
            ("paper_intents", "exit_plan_id", kwargs["exit_plan_id"], kwargs["exit_plan"]),
            ("paper_fills|paper_intents", "orderbook_snapshot_id", kwargs["orderbook_id"], kwargs["orderbook"]),
        )
        links: list[dict[str, Any]] = []
        for table, field, value, resolved in checks:
            if not value:
                links.append({"status": "MISSING_LINK", "table": table, "field": field, "value": None, "reason": "FIELD_EMPTY"})
            elif resolved is None:
                links.append({"status": "MISSING_LINK", "table": table, "field": field, "value": value, "reason": "REFERENCED_ROW_NOT_FOUND"})
        position = kwargs["position"]
        close = kwargs["close"]
        if (position.get("current_status") == "CLOSED" or position.get("closed_at")) and close is None:
            links.append({"status": "MISSING_LINK", "table": "paper_position_closes", "field": "position_id", "value": kwargs["paper_position_id"], "reason": "CLOSED_POSITION_WITHOUT_CLOSE_ROW"})
        return links


def _fetch_optional_by_text_id(conn: Any, table: str, column: str, value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    return _fetchone(conn, f"SELECT * FROM {table} WHERE {column} = %s", (value,))


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


def _table_exists(conn: Any, table: str) -> bool:
    try:
        row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
        return bool(row and row["table_name"])
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _missing_payout_fields(row: dict[str, Any] | None) -> list[str]:
    if not row:
        return ["PAYOUT_ODDS_EVALUATION_MISSING"]
    fields = [
        "implied_probability",
        "stake_usd",
        "quantity",
        "payout_if_win",
        "profit_if_win",
        "max_loss",
        "risk_reward",
        "break_even_probability",
    ]
    return [field for field in fields if row.get(field) is None]


def _freshness_status(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "UNKNOWN_FRESHNESS"
    statuses = {str(row.get("freshness_status") or "").upper() for row in rows}
    if statuses & {"REFRESH_REQUIRED", "EXPIRED", "UNKNOWN_FRESHNESS"}:
        return "REFRESH_REQUIRED"
    if "STALE" in statuses:
        return "STALE"
    if "FRESH" in statuses:
        return "FRESH"
    return "HISTORICAL_ONLY"


def _truth_state_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    permissions: dict[str, int] = {}
    for row in rows:
        state = str(row.get("truth_state") or "UNKNOWN")
        permission = str(row.get("decision_permission") or "UNKNOWN_PERMISSION")
        counts[state] = counts.get(state, 0) + 1
        permissions[permission] = permissions.get(permission, 0) + 1
    return {
        "truth_state_counts": counts,
        "decision_permission_counts": permissions,
        "can_authorize": permissions.get("CAN_AUTHORIZE", 0),
        "requires_refresh": permissions.get("MUST_REFRESH", 0),
        "historical_memory": counts.get("HISTORICAL_ONLY", 0),
    }


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _opinion_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "opinion_id": row.get("opinion_id"),
        "brain_name": row.get("brain_name"),
        "brain_type": row.get("brain_type"),
        "stance": row.get("stance"),
        "confidence": row.get("confidence"),
        "decision_bias": row.get("decision_bias"),
        "reasoning_summary": row.get("reasoning_summary"),
        "supporting_sources": row.get("supporting_sources_json"),
        "opposing_sources": row.get("opposing_sources_json"),
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
    if value.__class__.__name__ == "UUID":
        return str(value)
    return value
