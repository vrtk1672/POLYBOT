from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.data_foundation.contracts import OrderbookSnapshot
from app.events.envelope import EventEnvelope
from app.events.types import EventType
from app.repositories.event_store_repository import EventStoreRepository
from app.services.capital_efficiency import CapitalEfficiencyService
from app.services.exit_foundation import ExitFoundationService
from app.services.exit_hold_reasoning import ExitHoldReasoningService
from app.services.lifecycle_governance import LifecycleGovernanceGateService
from app.services.risk_evidence_mesh import RiskEvidenceMeshService
from app.services.same_market_side_guard import SameMarketSideGuardService


CONSUMERS = {
    "mesh_proof_liquidity_brain": "liquidity",
    "mesh_proof_risk_brain": "risk",
    "mesh_proof_exit_brain": "exit",
    "mesh_proof_capital_brain": "capital",
    "mesh_proof_lifecycle_brain": "lifecycle",
    "mesh_proof_coordinator": "coordinator",
}


class OrderbookMeshProofConsumer:
    """Minimal durable fanout proof for orderbook snapshot events.

    This is deliberately non-executing. It records source-backed opinions and a
    coordinator trace only; it never creates intents, orders, fills, or positions.
    """

    def __init__(self) -> None:
        self._events = EventStoreRepository()

    def record_snapshot_created(self, conn: Any, snapshot: OrderbookSnapshot) -> dict[str, Any] | None:
        if not _table_exists(conn, "event_log") or not _table_exists(conn, "brain_outputs") or not _table_exists(conn, "coordinator_decisions"):
            return None
        snapshot_row = conn.execute(
            "SELECT * FROM orderbook_snapshots WHERE orderbook_snapshot_id = %s ORDER BY id DESC LIMIT 1",
            (snapshot.orderbook_snapshot_id,),
        ).fetchone()
        if not snapshot_row:
            return None

        event = self._publish_orderbook_event(conn, snapshot, dict(snapshot_row))
        self._ensure_consumers(conn)
        reactions = self._record_brain_reactions(conn, event, dict(snapshot_row))
        coordinator = self._record_coordinator_trace(conn, event, reactions, dict(snapshot_row))
        return {
            "event_id": event.event_id,
            "correlation_id": event.correlation_id,
            "brain_reactions": reactions,
            "coordinator_decision_id": coordinator.get("coordinator_decision_id"),
        }

    def _publish_orderbook_event(self, conn: Any, snapshot: OrderbookSnapshot, row: dict[str, Any]) -> EventEnvelope:
        correlation_id = f"{snapshot.correlation_id or 'orderbook_snapshot'}:{snapshot.orderbook_snapshot_id}"
        metadata = row.get("metadata_json") or snapshot.metadata_json or {}
        candidate_id = metadata.get("candidate_id") or _candidate_for_snapshot(conn, row)
        payload = {
            "event_id": None,
            "correlation_id": correlation_id,
            "market_id": row.get("market_id"),
            "candidate_id": candidate_id,
            "side": row.get("side"),
            "token_id": row.get("token_id"),
            "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
            "orderbook_snapshot_pk": row.get("id"),
            "best_bid": _float(row.get("best_bid")),
            "best_ask": _float(row.get("best_ask")),
            "spread": _float(row.get("spread")),
            "depth": {
                "depth_1c": _float(row.get("depth_1c")),
                "depth_2c": _float(row.get("depth_2c")),
                "depth_5c": _float(row.get("depth_5c")),
                "total_bid_depth": _float(row.get("total_bid_depth")),
                "total_ask_depth": _float(row.get("total_ask_depth")),
            },
            "timestamp": _iso(row.get("collected_at") or row.get("snapshot_at") or row.get("created_at")),
            "source": row.get("source") or "orderbook_snapshots",
            "candidate_source": metadata.get("candidate_source"),
            "refresh_reason": metadata.get("refresh_reason"),
            "refresh_scope": metadata.get("refresh_scope") or ("CANDIDATE_SCOPED" if candidate_id else "MARKET_SCOPED"),
            "source_service": metadata.get("source_service") or "orderbook_snapshot_repository",
            "candidate_event_scope": metadata.get("candidate_event_scope") or ("CANDIDATE_TARGETED_REFRESH" if candidate_id else "MARKET_LEVEL"),
            "candidate_event_scoped": bool(candidate_id),
            "candidate_link_blocker": None if candidate_id else "MISSING_CANDIDATE_ID",
            "read_only": True,
            "no_trading_authority": True,
        }
        envelope = EventEnvelope(
            event_type=EventType.ORDERBOOK_SNAPSHOT_CREATED.value,
            aggregate_type="orderbook_snapshot",
            aggregate_id=str(row.get("orderbook_snapshot_id")),
            source_service="orderbook_snapshot_repository",
            correlation_id=correlation_id,
            cycle_id=snapshot.correlation_id,
            mode="DATA_ONLY",
            payload=payload,
            metadata={
                "phase": "minimal_event_mesh_proof",
                "source_table": "orderbook_snapshots",
                "source_record_id": str(row.get("id")),
                "no_execution": True,
            },
        )
        envelope.payload["event_id"] = envelope.event_id
        self._events.append_event(conn, envelope)
        return envelope

    def _ensure_consumers(self, conn: Any) -> None:
        if not _table_exists(conn, "event_consumers"):
            return
        for consumer_name, brain in CONSUMERS.items():
            conn.execute(
                """
                INSERT INTO event_consumers (
                    consumer_name, consumer_group, subscribed_event_types, status,
                    last_seen_at, metadata_json, updated_at
                )
                VALUES (%s, 'minimal_event_mesh_proof', ARRAY[%s]::text[], 'ACTIVE', now(), %s, now())
                ON CONFLICT (consumer_name) DO UPDATE SET
                    subscribed_event_types = EXCLUDED.subscribed_event_types,
                    status = 'ACTIVE',
                    last_seen_at = now(),
                    metadata_json = EXCLUDED.metadata_json,
                    updated_at = now()
                """,
                (
                    consumer_name,
                    EventType.ORDERBOOK_SNAPSHOT_CREATED.value,
                    Jsonb({"brain": brain, "phase": "minimal_event_mesh_proof", "no_execution": True}),
                ),
            )

    def _record_brain_reactions(self, conn: Any, event: EventEnvelope, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        reactions = []
        for reaction in (_liquidity_reaction(snapshot), _risk_reaction(snapshot), _exit_reaction(snapshot), _capital_reaction(conn)):
            reactions.append(self._insert_brain_reaction(conn, event, reaction))
        reactions.append(self._insert_brain_reaction(conn, event, _lifecycle_reaction(conn, event)))
        return reactions

    def _insert_brain_reaction(self, conn: Any, event: EventEnvelope, reaction: dict[str, Any]) -> dict[str, Any]:
        output_id = f"mesh_proof_{reaction['brain']}_{uuid4().hex}"
        conn.execute(
            """
            INSERT INTO brain_outputs (
                brain_output_id, brain, output_type, market_id, recommendation,
                confidence, urgency, risk_flags_json, reasoning_summary, status,
                ttl_seconds, correlation_id, generated_by, model_name,
                model_version, raw_payload_ref, metadata_json
            )
            VALUES (
                %(brain_output_id)s, %(brain)s, %(output_type)s, %(market_id)s,
                %(recommendation)s, %(confidence)s, %(urgency)s, %(risk_flags_json)s,
                %(reasoning_summary)s, %(status)s, %(ttl_seconds)s,
                %(correlation_id)s, 'minimal_event_mesh_proof', 'deterministic_mesh_proof',
                'phase_8', %(raw_payload_ref)s, %(metadata_json)s
            )
            """,
            {
                "brain_output_id": output_id,
                "brain": reaction["brain"],
                "output_type": reaction["output_type"],
                "market_id": event.payload.get("market_id"),
                "recommendation": reaction["recommendation"],
                "confidence": reaction["confidence"],
                "urgency": reaction["urgency"],
                "risk_flags_json": Jsonb(reaction["blockers"]),
                "reasoning_summary": reaction["summary"],
                "status": "ACTIVE" if reaction["state"] == "REACTED" else "PARTIAL",
                "ttl_seconds": 180,
                "correlation_id": event.correlation_id,
                "raw_payload_ref": f"event_log:{event.event_id}",
                "metadata_json": Jsonb({
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "candidate_id": event.payload.get("candidate_id"),
                    "token_id": event.payload.get("token_id"),
                    "side": event.payload.get("side"),
                    "reaction_state": reaction["state"],
                    "event_native_state": reaction.get("event_native_state", "EVENT_NATIVE"),
                    "capital_opinion_state": reaction.get("capital_opinion_state"),
                    "lifecycle_opinion_state": reaction.get("lifecycle_opinion_state"),
                    "available_capital": reaction.get("available_capital"),
                    "locked_capital": reaction.get("locked_capital"),
                    "open_exposure": reaction.get("open_exposure"),
                    "decision_source": reaction.get("decision_source"),
                    "source_created_at": reaction.get("source_created_at"),
                    "blockers": reaction["blockers"],
                    "warnings": reaction["warnings"],
                    "no_execution": True,
                }),
            },
        )
        reaction["brain_output_id"] = output_id
        self._record_delivery(conn, event, f"mesh_proof_{reaction['brain']}_brain", "SUCCESS", {"reaction_state": reaction["state"]})
        return reaction

    def _record_coordinator_trace(
        self,
        conn: Any,
        event: EventEnvelope,
        reactions: list[dict[str, Any]],
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        blockers = sorted({blocker for reaction in reactions for blocker in reaction["blockers"]})
        reacted = sum(1 for reaction in reactions if reaction["state"] == "REACTED")
        all_reacted = reacted == 5
        reaction_by_brain = {reaction.get("brain"): reaction for reaction in reactions}
        capital_state = str(reaction_by_brain.get("capital", {}).get("capital_opinion_state") or "CAPITAL_UNKNOWN")
        lifecycle_state = str(reaction_by_brain.get("lifecycle", {}).get("lifecycle_opinion_state") or "LIFECYCLE_UNKNOWN")
        price_blockers = [
            blocker
            for reaction in reactions
            if reaction.get("brain") in {"liquidity", "risk", "exit"}
            for blocker in reaction.get("blockers", [])
        ]
        conflicts: list[dict[str, Any]] = []
        if price_blockers:
            decision = "PRICE_BLOCKED"
            final_state = "DATA_DEGRADED"
            reason = f"Orderbook mesh proof blocked by {', '.join(sorted(set(price_blockers)))}."
        elif capital_state in {"CAPITAL_MISSING", "CAPITAL_UNKNOWN", "CAPITAL_PARTIAL"}:
            decision = "WAITING_FOR_CAPITAL"
            final_state = "INSUFFICIENT_DATA"
            reason = "Capital brain produced an event-native opinion, but capital evidence is incomplete."
        elif capital_state == "CAPITAL_BLOCKED":
            decision = "CAPITAL_BLOCKED"
            final_state = "PAPER_CANDIDATE_BLOCKED"
            reason = "Capital brain blocked progress for this event-native mesh session."
        elif lifecycle_state in {"LIFECYCLE_MISSING", "LIFECYCLE_UNKNOWN", "LIFECYCLE_PARTIAL", "LIFECYCLE_STALE"}:
            decision = "WAITING_FOR_LIFECYCLE"
            final_state = "INSUFFICIENT_DATA"
            reason = "Lifecycle brain produced an event-native opinion, but lifecycle evidence is incomplete or stale."
        elif lifecycle_state == "LIFECYCLE_DENIED":
            decision = "LIFECYCLE_BLOCKED"
            final_state = "PAPER_CANDIDATE_BLOCKED"
            reason = "Lifecycle brain denied progress for this event-native mesh session."
        elif all_reacted:
            decision = "PRICE_READY"
            final_state = "WATCH"
            reason = "Liquidity, risk, exit, capital, and lifecycle brains reacted to the same orderbook snapshot event."
        else:
            decision = "WAITING_FOR_EVIDENCE"
            final_state = "REVIEW_REQUIRED"
            reason = "One or more brain reactions were incomplete."
        consensus_state = _consensus_state(decision)

        coordinator_id = f"mesh_proof_coord_{uuid4().hex}"
        conn.execute(
            """
            INSERT INTO coordinator_decisions (
                coordinator_decision_id, market_id, final_state, primary_reason,
                confidence, urgency, conflicts_detected, governor_required,
                execution_allowed, approved_actions_json, blocked_actions_json,
                required_reviews_json, risk_flags_json, source_brain_count,
                input_output_count, conflict_count, correlation_id, ttl_seconds,
                status, metadata_json
            )
            VALUES (
                %(coordinator_decision_id)s, %(market_id)s, %(final_state)s,
                %(primary_reason)s, %(confidence)s, %(urgency)s, false, true,
                false, %(approved_actions_json)s, %(blocked_actions_json)s,
                %(required_reviews_json)s, %(risk_flags_json)s, %(source_brain_count)s,
                %(input_output_count)s, %(conflict_count)s, %(correlation_id)s, 180, 'ACTIVE',
                %(metadata_json)s
            )
            """,
            {
                "coordinator_decision_id": coordinator_id,
                "market_id": event.payload.get("market_id"),
                "final_state": final_state,
                "primary_reason": reason,
                "confidence": 0.72 if all_reacted and not blockers else 0.55,
                "urgency": 0.4,
                "approved_actions_json": Jsonb(["WATCH"] if decision == "PRICE_READY" else ["REVIEW"]),
                "blocked_actions_json": Jsonb(["PAPER_ENTRY", "LIVE_ENTRY", "ORDER_CREATION", "POSITION_OPEN"]),
                "required_reviews_json": Jsonb(_required_to_progress(blockers)),
                "risk_flags_json": Jsonb(blockers),
                "source_brain_count": reacted,
                "input_output_count": len(reactions),
                "conflict_count": len(conflicts),
                "correlation_id": event.correlation_id,
                "metadata_json": Jsonb({
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "decision": decision,
                    "mesh_consensus_state": consensus_state,
                    "coordinator_state": "DECISION_CREATED" if all_reacted else "PARTIAL_DECISION",
                    "capital_opinion_state": capital_state,
                    "lifecycle_opinion_state": lifecycle_state,
                    "conflicts": conflicts,
                    "brain_reactions": reactions,
                    "snapshot": {
                        "orderbook_snapshot_id": snapshot.get("orderbook_snapshot_id"),
                        "token_id": snapshot.get("token_id"),
                        "side": snapshot.get("side"),
                        "best_bid": _float(snapshot.get("best_bid")),
                        "best_ask": _float(snapshot.get("best_ask")),
                        "spread": _float(snapshot.get("spread")),
                    },
                    "no_execution": True,
                }),
            },
        )
        for reaction in reactions:
            if reaction.get("brain_output_id"):
                conn.execute(
                    """
                    INSERT INTO coordinator_decision_inputs (
                        coordinator_decision_id, brain_output_id, brain, input_role,
                        input_recommendation, input_confidence
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        coordinator_id,
                        reaction["brain_output_id"],
                        reaction["brain"],
                        "mesh_proof_reaction",
                        reaction["recommendation"],
                        reaction["confidence"],
                    ),
                )
        self._record_delivery(conn, event, "mesh_proof_coordinator", "SUCCESS", {"decision": decision})
        return {"coordinator_decision_id": coordinator_id, "decision": decision, "reason": reason}

    def _record_delivery(self, conn: Any, event: EventEnvelope, consumer_name: str, status: str, metadata: dict[str, Any]) -> None:
        if not _table_exists(conn, "event_delivery_attempts"):
            return
        conn.execute(
            """
            INSERT INTO event_delivery_attempts (
                event_id, consumer_name, attempt_number, status, finished_at, metadata_json
            )
            VALUES (%s, %s, 1, %s, now(), %s)
            """,
            (event.event_id, consumer_name, status, Jsonb({"phase": "minimal_event_mesh_proof", **metadata})),
        )
        if _table_exists(conn, "event_consumers"):
            conn.execute(
                """
                UPDATE event_consumers
                SET last_event_id=%s, last_success_at=now(), updated_at=now()
                WHERE consumer_name=%s
                """,
                (event.event_id, consumer_name),
            )


def _liquidity_reaction(snapshot: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    bid = _float(snapshot.get("best_bid"))
    ask = _float(snapshot.get("best_ask"))
    spread = _float(snapshot.get("spread"))
    depth = max(_float(snapshot.get("depth_1c")) or 0, _float(snapshot.get("total_bid_depth")) or 0, _float(snapshot.get("total_ask_depth")) or 0)
    if bid is None or ask is None:
        blockers.append("MISSING_BID_ASK")
    if spread is None:
        warnings.append("MISSING_SPREAD")
    elif spread > 0.08:
        blockers.append("SPREAD_TOO_WIDE")
    if depth <= 0:
        warnings.append("DEPTH_MISSING_OR_ZERO")
    state = "REACTED" if not blockers else "BLOCKED_MISSING_DATA"
    return {
        "brain": "liquidity",
        "state": state,
        "output_type": "CAUTION" if blockers else "WATCH",
        "recommendation": "OBSERVE_LIQUIDITY",
        "confidence": 0.82 if not blockers else 0.4,
        "urgency": 0.35,
        "summary": f"Liquidity saw bid={bid}, ask={ask}, spread={spread}, depth={depth}.",
        "blockers": blockers,
        "warnings": warnings,
    }


def _risk_reaction(snapshot: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    spread = _float(snapshot.get("spread"))
    if str(snapshot.get("snapshot_status") or "").upper() not in {"OK", "PARTIAL"}:
        blockers.append("ORDERBOOK_STATUS_NOT_USABLE")
    if bool(snapshot.get("is_stale")):
        blockers.append("ORDERBOOK_STALE")
    if spread is None:
        warnings.append("SPREAD_MISSING")
    elif spread > 0.08:
        blockers.append("PRICE_RISK_SPREAD_TOO_WIDE")
    state = "REACTED" if not blockers else "BLOCKED_MISSING_DATA"
    return {
        "brain": "risk",
        "state": state,
        "output_type": "RISK_WARNING" if blockers else "WATCH",
        "recommendation": "OBSERVE_RISK",
        "confidence": 0.78 if not blockers else 0.45,
        "urgency": 0.4,
        "summary": f"Risk evaluated orderbook status={snapshot.get('snapshot_status')} stale={snapshot.get('is_stale')} spread={spread}.",
        "blockers": blockers,
        "warnings": warnings,
    }


def _exit_reaction(snapshot: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    side = str(snapshot.get("side") or "").upper()
    bid = _float(snapshot.get("best_bid"))
    ask = _float(snapshot.get("best_ask"))
    exit_price = bid if side == "YES" else ask if side == "NO" else None
    if side not in {"YES", "NO"}:
        blockers.append("MISSING_SIDE")
    if exit_price is None:
        blockers.append("EXIT_PRICE_MISSING")
    if _float(snapshot.get("total_bid_depth")) in (None, 0.0) and _float(snapshot.get("total_ask_depth")) in (None, 0.0):
        warnings.append("EXIT_DEPTH_UNKNOWN")
    state = "REACTED" if not blockers else "BLOCKED_MISSING_DATA"
    return {
        "brain": "exit",
        "state": state,
        "output_type": "EXIT_REVIEW_HINT",
        "recommendation": "OBSERVE_EXIT_PATH",
        "confidence": 0.76 if not blockers else 0.42,
        "urgency": 0.35,
        "summary": f"Exit evaluated side={side}, exit_price={exit_price}, bid={bid}, ask={ask}.",
        "blockers": blockers,
        "warnings": warnings,
    }


def _capital_reaction(conn: Any) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    account: dict[str, Any] | None = None
    if _table_exists(conn, "paper_accounts"):
        row = conn.execute(
            """
            SELECT *
            FROM paper_accounts
            WHERE account_id = 'paper_default'
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ).fetchone()
        account = dict(row) if row else None
    if not account:
        blockers.append("CAPITAL_SOURCE_MISSING")
        state = "CAPITAL_MISSING"
    else:
        available = _float(account.get("available_balance"))
        locked = _float(account.get("locked_balance")) or 0.0
        exposure = _float(account.get("open_exposure")) or 0.0
        max_open = int(account.get("max_open_positions") or 0)
        open_positions = _open_paper_positions(conn)
        if available is None:
            blockers.append("CAPITAL_AVAILABLE_BALANCE_MISSING")
            state = "CAPITAL_MISSING"
        elif max_open > 0 and open_positions >= max_open:
            blockers.append("MAX_OPEN_POSITIONS")
            state = "CAPITAL_BLOCKED"
        elif available <= 0:
            blockers.append("CAPITAL_NOT_AVAILABLE")
            state = "CAPITAL_BLOCKED"
        else:
            state = "CAPITAL_OK"
        return {
            "brain": "capital",
            "state": "REACTED",
            "event_native_state": "EVENT_NATIVE",
            "capital_opinion_state": state,
            "output_type": "CAPITAL_OPINION",
            "recommendation": "OBSERVE_CAPITAL",
            "confidence": 0.74 if state == "CAPITAL_OK" else 0.52,
            "urgency": 0.35,
            "summary": f"Capital evaluated available={available}, locked={locked}, exposure={exposure}, open_positions={open_positions}.",
            "available_capital": available,
            "locked_capital": locked,
            "open_exposure": exposure,
            "blockers": blockers,
            "warnings": warnings,
        }
    return {
        "brain": "capital",
        "state": "REACTED",
        "event_native_state": "EVENT_NATIVE",
        "capital_opinion_state": state,
        "output_type": "CAPITAL_OPINION",
        "recommendation": "OBSERVE_CAPITAL",
        "confidence": 0.35,
        "urgency": 0.4,
        "summary": "Capital could not locate paper_default account evidence for this event-native mesh session.",
        "available_capital": None,
        "locked_capital": None,
        "open_exposure": None,
        "blockers": blockers,
        "warnings": warnings,
    }


def _lifecycle_reaction(conn: Any, event: EventEnvelope) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    payload = event.payload
    if payload.get("candidate_id"):
        refreshed_inputs = _refresh_candidate_lifecycle_inputs(conn, event, warnings)
        try:
            LifecycleGovernanceGateService().evaluate_subject_with_conn(
                conn,
                subject_type="PAPER_CANDIDATE",
                subject_id=str(payload.get("candidate_id")),
                request_action="PAPER_INTENT",
                allow_build=True,
                force_build=True,
                write_decision=True,
                metadata={
                    "source_layer": "event_native_orderbook_mesh",
                    "event_id": event.event_id,
                    "correlation_id": event.correlation_id,
                    "market_id": payload.get("market_id"),
                    "side": payload.get("side"),
                    "token_id": payload.get("token_id"),
                    "data_only": True,
                    "no_execution": True,
                    **refreshed_inputs,
                },
            )
        except Exception as exc:
            warnings.append(f"LIFECYCLE_REEVALUATION_FAILED:{type(exc).__name__}")
    row = _latest_lifecycle_decision(conn, payload)
    if not row:
        blockers.append("LIFECYCLE_GOVERNANCE_MISSING")
        state = "LIFECYCLE_MISSING"
        summary = "Lifecycle governance decision is unavailable for this event-native mesh session."
        decision_source = None
        source_created_at = None
    else:
        decision = dict(row)
        source_created_at = _iso(decision.get("created_at"))
        critical = list(decision.get("critical_blockers_json") or [])
        optional = list(decision.get("optional_missing_json") or []) + list(decision.get("context_dependent_missing_json") or [])
        blockers.extend(str(item) for item in critical)
        warnings.extend(str(item) for item in optional)
        allowed = bool(decision.get("allow_paper_intent") or decision.get("allow_paper_execution"))
        actionability = str(decision.get("actionability_class") or "").upper()
        if allowed and not critical:
            state = "LIFECYCLE_ALLOWED"
        elif actionability in {"ACTIONABLE_SMALL_PAPER", "ACTIONABLE", "READY"} and not critical:
            state = "LIFECYCLE_PARTIAL"
            warnings.append("LIFECYCLE_ALLOW_FLAGS_MISSING")
        else:
            state = "LIFECYCLE_DENIED"
            if not blockers:
                blockers.append("LIFECYCLE_GOVERNANCE_DENIED")
        decision_source = decision.get("decision_id")
        summary = f"Lifecycle evaluated actionability={decision.get('actionability_class')} allow_intent={decision.get('allow_paper_intent')} allow_execution={decision.get('allow_paper_execution')}."
    return {
        "brain": "lifecycle",
        "state": "REACTED",
        "event_native_state": "EVENT_NATIVE",
        "lifecycle_opinion_state": state,
        "output_type": "LIFECYCLE_OPINION",
        "recommendation": "OBSERVE_LIFECYCLE",
        "confidence": 0.72 if state == "LIFECYCLE_ALLOWED" else 0.5,
        "urgency": 0.4,
        "summary": summary,
        "decision_source": decision_source,
        "source_created_at": source_created_at,
        "blockers": blockers,
        "warnings": warnings,
    }


def _refresh_candidate_lifecycle_inputs(conn: Any, event: EventEnvelope, warnings: list[str]) -> dict[str, Any]:
    """Refresh derived DATA_ONLY lifecycle inputs for a candidate-scoped event.

    These services write only observational/evaluation truth. They do not create
    intents, orders, fills, positions, live orders, or capital mutations.
    """
    payload = event.payload
    candidate_id = str(payload.get("candidate_id") or "")
    if not candidate_id:
        return {}

    candidate = _candidate_row(conn, candidate_id) or {}
    market_id = str(payload.get("market_id") or candidate.get("market_id") or "")
    side = str(payload.get("side") or candidate.get("side") or "").upper()
    refresh_metadata = {
        "source_layer": "event_native_orderbook_mesh",
        "event_id": event.event_id,
        "correlation_id": event.correlation_id,
        "token_id": payload.get("token_id") or candidate.get("expected_token_id"),
        "data_only": True,
        "no_execution": True,
    }
    refreshed: dict[str, Any] = {"candidate_lifecycle_input_refresh": {"attempted": True}}

    if market_id and side:
        try:
            guard = SameMarketSideGuardService().evaluate(
                conn,
                market_id=market_id,
                proposed_side=side,
                proposed_candidate_id=candidate_id,
                coordinator_decision_id=candidate.get("coordinator_decision_id"),
                evidence={"event_id": event.event_id, "correlation_id": event.correlation_id},
                metadata=refresh_metadata,
                write_decision=True,
                dry_run=False,
            )
            refreshed["same_market_guard_decision"] = guard.to_api_dict()
        except Exception as exc:
            warnings.append(f"SAME_MARKET_REVALIDATION_FAILED:{type(exc).__name__}")
    else:
        warnings.append("SAME_MARKET_REVALIDATION_SKIPPED_MISSING_MARKET_OR_SIDE")

    for label, service in (
        ("RISK_EVIDENCE_REVALIDATION", RiskEvidenceMeshService()),
        ("EXIT_HOLD_REVALIDATION", ExitHoldReasoningService()),
        ("CAPITAL_EFFICIENCY_REVALIDATION", CapitalEfficiencyService()),
    ):
        try:
            result = service.evaluate_subject_with_conn(
                conn,
                subject_type="PAPER_CANDIDATE",
                subject_id=candidate_id,
                dry_run=False,
            )
            refreshed[label.lower()] = result
        except Exception as exc:
            warnings.append(f"{label}_FAILED:{type(exc).__name__}")

    try:
        refreshed["exit_foundation_candidate_refresh"] = ExitFoundationService().build_candidate_exit_plan_with_conn(
            conn,
            candidate_id=candidate_id,
            event_id=event.event_id,
            correlation_id=event.correlation_id,
            write_plan=True,
        )
    except Exception as exc:
        warnings.append(f"EXIT_FOUNDATION_CANDIDATE_REFRESH_FAILED:{type(exc).__name__}")

    return refreshed


def _candidate_row(conn: Any, candidate_id: str) -> dict[str, Any] | None:
    if not candidate_id or not _table_exists(conn, "paper_eligibility_candidates"):
        return None
    row = conn.execute(
        """
        SELECT *
        FROM paper_eligibility_candidates
        WHERE eligibility_id = %s
        ORDER BY updated_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        (candidate_id,),
    ).fetchone()
    return dict(row) if row else None


def _candidate_for_snapshot(conn: Any, row: dict[str, Any]) -> str | None:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return None
    candidates = conn.execute(
        """
        SELECT eligibility_id
        FROM paper_eligibility_candidates
        WHERE market_id = %s
          AND upper(side) = upper(%s)
          AND (
              expected_token_id = %s
              OR orderbook_snapshot_id = %s
              OR evidence->'trusted_orderbook'->>'expected_token_id' = %s
        )
        ORDER BY updated_at DESC NULLS LAST, id DESC
        LIMIT 2
        """,
        (row.get("market_id"), row.get("side"), row.get("token_id"), row.get("id"), row.get("token_id")),
    ).fetchall()
    if len(candidates) == 1:
        return str(candidates[0]["eligibility_id"])
    return None


def _latest_lifecycle_decision(conn: Any, payload: dict[str, Any]) -> Any | None:
    if not _table_exists(conn, "lifecycle_governance_decisions"):
        return None
    if payload.get("candidate_id"):
        row = conn.execute(
            """
            SELECT *
            FROM lifecycle_governance_decisions
            WHERE subject_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (payload.get("candidate_id"),),
        ).fetchone()
        if row:
            return row
    if payload.get("market_id"):
        clauses = ["market_id = %s"]
        params: list[Any] = [payload.get("market_id")]
        if payload.get("side"):
            clauses.append("(side IS NULL OR upper(side) = %s)")
            params.append(str(payload.get("side")).upper())
        if payload.get("token_id"):
            clauses.append("(token_id IS NULL OR token_id = %s)")
            params.append(payload.get("token_id"))
        return conn.execute(
            f"""
            SELECT *
            FROM lifecycle_governance_decisions
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
    return None


def _open_paper_positions(conn: Any) -> int:
    if not _table_exists(conn, "paper_positions"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM paper_positions
        WHERE closed_at IS NULL
          AND current_status IN ('OPEN','EXIT_PENDING')
          AND COALESCE(excluded_from_active_paper_truth, false) = false
        """
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _consensus_state(decision: str) -> str:
    if decision == "PRICE_READY":
        return "CONSENSUS_READY"
    if decision == "CAPITAL_BLOCKED":
        return "CONSENSUS_BLOCKED"
    if decision == "LIFECYCLE_BLOCKED":
        return "CONSENSUS_BLOCKED"
    if decision == "WAITING_FOR_CAPITAL":
        return "CONSENSUS_WAITING_FOR_CAPITAL"
    if decision == "WAITING_FOR_LIFECYCLE":
        return "CONSENSUS_WAITING_FOR_LIFECYCLE"
    if decision in {"PRICE_BLOCKED", "CONFLICT"}:
        return "CONSENSUS_BLOCKED"
    return "CONSENSUS_PARTIAL"


def _required_to_progress(blockers: list[str]) -> list[str]:
    if not blockers:
        return ["Keep orderbook fresh within execution TTL before any paper decision."]
    required: list[str] = []
    if any("SPREAD" in blocker for blocker in blockers):
        required.append("Spread must narrow before price readiness can progress.")
    if any("MISSING" in blocker for blocker in blockers):
        required.append("Missing bid, ask, side, or exit price evidence must be refreshed.")
    if "ORDERBOOK_STALE" in blockers:
        required.append("Orderbook must be refreshed within execution TTL.")
    return required or ["Brain blockers must clear before candidate progress."]


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return None


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None
