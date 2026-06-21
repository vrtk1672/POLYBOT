from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.last_mile_orderbook_refresh import (
    DEFAULT_ORDERBOOK_TTL_SECONDS,
    LastMileOrderbookRefreshService,
    ensure_tables as ensure_last_mile_orderbook_tables,
    is_fresh_orderbook,
    latest_matching_orderbook,
    orderbook_age_seconds,
)
from app.services.paper_session import active_paper_session_id
from app.services.paper_defense import (
    BASE_PAPER_THRESHOLD,
    apply_defense_to_blockers,
    get_active_profile,
    record_learning_decision,
)
from app.services.same_market_arbitration import SameMarketSideArbitrator


FRESH_ORDERBOOK_SECONDS = DEFAULT_ORDERBOOK_TTL_SECONDS
PAPER_OBSERVATION_SCORE_THRESHOLD = Decimal("60")
SUPPORTED_EDGE_STATES = {"EDGE_SUPPORTED"}
SUPPORTED_THESIS_STATES = {"THESIS_SUPPORTED", "VALID"}
WATCH_THESIS_STATES = {"THESIS_WATCH", "WATCH"}
RISK_BLOCK_STATES = {"RISK_BLOCKED", "RISK_BLOCK", "RISK_DENIED"}
RISK_REVIEW_STATES = {"RISK_REVIEW", "RISK_WATCH"}
CAPITAL_BLOCK_STATES = {"CAPITAL_BLOCK", "CAPITAL_BLOCKED", "CAPITAL_DENIED"}
CAPITAL_WATCH_STATES = {"CAPITAL_WATCH", "CAPITAL_REVIEW"}
EXIT_READY_STATES = {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}
LIFECYCLE_BLOCK_STATES = {"BLOCKED", "DENIED", "LIFECYCLE_DENIED", "HARD_BLOCKED"}
LIFECYCLE_RESEARCH_STATES = {"DATA_ONLY_RESEARCH", "WATCH", "UNKNOWN"}
FRESH_ORDERBOOK_STATES = {"FRESH", "ORDERBOOK_FRESH"}
TOKEN_VERIFIED_STATES = {"TOKENS_VERIFIED", "TOKEN_SIDE_DIRECT", "SIDE_DIRECTIONAL_YES", "SIDE_DIRECTIONAL_NO"}
VALID_SCOPE_STATES = {"CANDIDATE_SCOPED", "CANDIDATE_ACTIONABLE", "CANDIDATE_TARGETED_REFRESH"}


class PaperRuntimeDecisionService:
    """Bridge policy-reviewed research decisions into the unified PAPER runtime.

    The service does not create paper intents or orders. It persists a canonical
    ENTER/WATCH/BLOCK decision for PAPER mode using existing Mesh-reviewed,
    policy-reviewed evidence. Live permission remains false on every row.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def refresh(self, *, limit: int = 100, force: bool = False) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"paper_runtime_decision_{uuid4().hex}"
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "run_id": run_id, "candidates_reviewed": 0}
        limit = max(1, min(int(limit or 100), 500))
        with self._factory.connect() as conn, conn.transaction():
            _ensure_tables(conn)
            before = _safety_counts(conn)
            conn.execute("UPDATE paper_runtime_decisions SET is_current_batch = false")
            rows = _candidate_rows(conn, limit=limit, force=force)
            seen_market_side: set[tuple[str, str]] = set()
            stats: Counter[str] = Counter()
            unique_markets: set[str] = set()
            unique_market_sides: set[tuple[str, str]] = set()
            errors: list[str] = []
            pending_decisions: list[dict[str, Any]] = []
            for row in rows:
                try:
                    decision = build_paper_runtime_decision(conn, row, seen_market_side=seen_market_side)
                    duplicate_group_size = int(row.get("duplicate_group_size") or 1)
                    stats["duplicate_suppressed_count"] += max(0, duplicate_group_size - 1)
                    stats["candidates_reviewed"] += 1
                    pending_decisions.append(decision)
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
            decisions = _arbitrate_same_market_opposing_enters(pending_decisions, conn=conn)
            for decision in decisions:
                try:
                    if decision.get("market_id"):
                        unique_markets.add(str(decision["market_id"]))
                    if decision.get("market_id") and decision.get("side"):
                        unique_market_sides.add((str(decision["market_id"]), str(decision["side"])))
                    _upsert_decision(conn, decision)
                    record_learning_decision(conn, decision)
                    stats[f"{str(decision['decision']).lower()}_count"] += 1
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
            after = _safety_counts(conn)
            status = "OK" if not errors else "PARTIAL" if stats["candidates_reviewed"] else "ERROR"
            _insert_run(
                conn,
                run_id=run_id,
                status=status,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                latest_error=errors[0] if errors else None,
                metadata={
                    "force": force,
                    "limit": limit,
                    "execution_mode": "PAPER",
                    "paper_is_execution_adapter_only": True,
                    "live_enter_allowed": False,
                    "safety_before": before,
                    "safety_after": after,
                    "trading_mutation": _trading_mutation(before, after),
                    "errors": errors[:5],
                    "selection_policy": "BEST_PER_MARKET_SIDE_THEN_DIVERSITY_RANK",
                    "unique_market_count": len(unique_markets),
                    "unique_market_side_count": len(unique_market_sides),
                    "duplicate_suppressed_count": int(stats["duplicate_suppressed_count"]),
                },
                **stats,
            )
        return {
            "status": status,
            "run_id": run_id,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "candidates_reviewed": int(stats["candidates_reviewed"]),
            "enter_count": int(stats["enter_count"]),
            "watch_count": int(stats["watch_count"]),
            "blocked_count": int(stats["block_count"]),
            "unique_market_count": len(unique_markets),
            "unique_market_side_count": len(unique_market_sides),
            "duplicate_suppressed_count": int(stats["duplicate_suppressed_count"]),
            "errors": errors[:5],
        }

    def list_for_intent_gate(self, conn: Any, *, limit: int = 100) -> list[dict[str, Any]]:
        _ensure_tables(conn)
        rows = conn.execute(
            """
            SELECT *
            FROM paper_runtime_decisions
            WHERE execution_mode='PAPER'
              AND is_current_batch IS TRUE
            ORDER BY
                CASE decision WHEN 'ENTER' THEN 0 WHEN 'WATCH' THEN 1 ELSE 2 END,
                diversity_score DESC,
                opportunity_score DESC,
                updated_at DESC,
                id DESC
            LIMIT %s
            """,
            (max(1, min(int(limit or 100), 500)),),
        ).fetchall()
        return [_decision_as_gate_candidate(dict(row)) for row in rows]

    def summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "total_decisions": 0}
        with self._factory.connect() as conn:
            _ensure_tables(conn)
            counts = dict(
                conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE decision='ENTER') AS enter_count,
                        COUNT(*) FILTER (WHERE decision='WATCH') AS watch_count,
                        COUNT(*) FILTER (WHERE decision='BLOCK') AS blocked_count,
                        COUNT(*) FILTER (WHERE paper_enter_allowed) AS paper_enter_allowed_count,
                        COUNT(DISTINCT market_id) AS unique_market_count,
                        COUNT(DISTINCT market_id || ':' || side) AS unique_market_side_count,
                        COALESCE(SUM(duplicate_suppressed_count), 0) AS duplicate_suppressed_count,
                        AVG(opportunity_score) AS avg_score
                    FROM paper_runtime_decisions
                    WHERE is_current_batch IS TRUE
                    """
                ).fetchone()
                or {}
            )
            latest_run = _latest_run(conn)
            top = conn.execute(
                """
                SELECT decision_id, market_id, side, opportunity_score, decision,
                       paper_enter_allowed, blockers_json, warnings_json, updated_at
                FROM paper_runtime_decisions
                WHERE is_current_batch IS TRUE
                ORDER BY opportunity_score DESC, updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            blockers = _json_array_counts(conn, "blockers_json", limit=limit)
        return {
            "status": "REAL" if int(counts.get("total") or 0) else "MISSING",
            "total_decisions": int(counts.get("total") or 0),
            "enter_count": int(counts.get("enter_count") or 0),
            "watch_count": int(counts.get("watch_count") or 0),
            "blocked_count": int(counts.get("blocked_count") or 0),
            "paper_enter_allowed_count": int(counts.get("paper_enter_allowed_count") or 0),
            "unique_market_count": int(counts.get("unique_market_count") or 0),
            "unique_market_side_count": int(counts.get("unique_market_side_count") or 0),
            "duplicate_suppressed_count": int(counts.get("duplicate_suppressed_count") or 0),
            "average_score": round(float(counts.get("avg_score") or 0), 2),
            "top_blockers": blockers,
            "latest_run": _json_safe(latest_run) if latest_run else None,
            "top_decisions": [_json_safe(dict(row)) for row in top],
            "paper_is_execution_adapter_only": True,
            "live_enter_allowed": False,
        }


def build_paper_runtime_decision(
    conn: Any,
    row: dict[str, Any],
    *,
    seen_market_side: set[tuple[str, str]] | None = None,
    last_mile_orderbook_refresh: LastMileOrderbookRefreshService | None = None,
) -> dict[str, Any]:
    seen_market_side = seen_market_side if seen_market_side is not None else set()
    review_id = str(row.get("paper_observation_policy_review_id") or "")
    market_id = _text(row.get("market_id"))
    condition_id = _text(row.get("condition_id"))
    side = _upper(row.get("side"))
    token_id = _text(row.get("token_id"))
    score = _decimal(row.get("opportunity_score"))
    edge_state = _upper(row.get("edge_state"))
    thesis_state = _upper(row.get("thesis_state"))
    risk_state = _upper(row.get("risk_state"))
    capital_state = _upper(row.get("capital_state"))
    exit_state = _upper(row.get("exit_state"))
    lifecycle_state = _upper(row.get("lifecycle_state"))
    orderbook_state = _upper(row.get("orderbook_state"))
    token_state = _upper(row.get("token_verification_state"))
    scope_state = _upper(row.get("candidate_event_scope_state"))
    lineage_state = _upper(row.get("lineage_state"))
    hard = _list(row.get("hard_blockers_json"))
    policy_blockers = _list(row.get("policy_blockers_json"))
    soft = _list(row.get("soft_blockers_json"))
    policy_state = _upper(row.get("observation_policy_state"))
    lineage = _dict(row.get("lineage_json"))
    duplicate_group_size = int(row.get("duplicate_group_size") or 1)
    market_side_rank = int(row.get("market_side_rank") or 1)
    diversity_score = _decimal(row.get("diversity_score"))

    blockers: list[str] = []
    warnings: list[str] = []
    required: list[str] = []

    if not bool(row.get("observation_allowed_by_policy")) and policy_state != "OBSERVATION_POLICY_WATCH":
        blockers.append("OBSERVATION_POLICY_NOT_ALLOWED")
    elif policy_state == "OBSERVATION_POLICY_WATCH":
        warnings.append("OBSERVATION_POLICY_WATCH_NOT_ENTERABLE")
    if _upper(row.get("decision_band")) != "PAPER_OBSERVATION":
        if policy_state == "OBSERVATION_POLICY_WATCH":
            warnings.append("DECISION_BAND_NOT_PAPER_OBSERVATION")
        else:
            blockers.append("DECISION_BAND_NOT_PAPER_OBSERVATION")
    if edge_state not in SUPPORTED_EDGE_STATES:
        blockers.append("EDGE_NOT_SUPPORTED")
    if thesis_state in WATCH_THESIS_STATES:
        warnings.append("THESIS_WATCH_ALLOWED_FOR_PAPER_LEARNING")
    elif thesis_state not in SUPPORTED_THESIS_STATES:
        blockers.append("THESIS_NOT_SUPPORTED")
    defense_profile = get_active_profile(conn)
    if score < defense_profile.adjusted_threshold:
        blockers.append("OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD")
    if risk_state in RISK_BLOCK_STATES:
        blockers.append("RISK_HARD_BLOCKED")
    elif risk_state in RISK_REVIEW_STATES:
        warnings.append("RISK_REVIEW_ALLOWED_FOR_PAPER_LEARNING")
    if capital_state in CAPITAL_BLOCK_STATES:
        blockers.append("CAPITAL_HARD_BLOCKED")
    elif capital_state in CAPITAL_WATCH_STATES:
        warnings.append("CAPITAL_WATCH_ALLOWED_FOR_PAPER_LEARNING")
    if exit_state not in EXIT_READY_STATES:
        blockers.append("EXIT_NOT_READY")
    if lifecycle_state in LIFECYCLE_BLOCK_STATES:
        blockers.append("LIFECYCLE_HARD_BLOCKED")
    elif lifecycle_state in LIFECYCLE_RESEARCH_STATES:
        warnings.append("DATA_ONLY_RESEARCH_ALLOWED_PAPER_ADAPTER_ONLY")
    if orderbook_state not in FRESH_ORDERBOOK_STATES:
        blockers.append("ORDERBOOK_NOT_FRESH")
    if token_state not in TOKEN_VERIFIED_STATES:
        blockers.append("TOKEN_SIDE_NOT_VERIFIED")
    if scope_state and scope_state not in VALID_SCOPE_STATES:
        blockers.append("CANDIDATE_EVENT_SCOPE_NOT_SCOPED")
    if lineage_state != "COMPLETE":
        blockers.append("LINEAGE_NOT_COMPLETE")
    if side not in {"YES", "NO"}:
        blockers.append("INVALID_SIDE")
    if not market_id:
        blockers.append("MISSING_MARKET_ID")
    if not token_id:
        blockers.append("MISSING_TOKEN_ID")
    if hard:
        blockers.append("EXISTING_HARD_BLOCKERS_PRESENT")
        blockers.extend(str(item).upper() for item in hard)
    if policy_state == "OBSERVATION_POLICY_WATCH":
        warnings.extend(str(item).upper() for item in policy_blockers)
    else:
        blockers.extend(str(item).upper() for item in policy_blockers)
    warnings.extend(str(item).upper() for item in soft)

    if any(bool(row.get(flag)) for flag in ("execution_allowed", "paper_allowed", "shadow_allowed", "live_allowed")):
        blockers.append("SOURCE_REVIEW_EXECUTION_FLAG_TRUE")
    if duplicate_group_size > 1:
        warnings.append(f"DUPLICATE_MARKET_SIDE_SEEDS_SUPPRESSED:{duplicate_group_size - 1}")

    decision_id = _decision_id(review_id or str(row.get("proactive_candidate_seed_id") or uuid4().hex))
    orderbook = latest_matching_orderbook(conn, market_id=market_id, token_id=token_id, side=side)
    pre_refresh_age_seconds = orderbook_age_seconds(orderbook)
    last_mile_refresh_result: dict[str, Any] = {
        "attempted": False,
        "state": "NOT_NEEDED" if is_fresh_orderbook(orderbook, ttl_seconds=FRESH_ORDERBOOK_SECONDS) else "NOT_ATTEMPTED",
        "error": None,
        "ttl_seconds": FRESH_ORDERBOOK_SECONDS,
        "pre_refresh_snapshot_id": orderbook.get("id") if orderbook else None,
        "pre_refresh_age_seconds": pre_refresh_age_seconds,
        "post_refresh_snapshot_id": orderbook.get("id") if orderbook else None,
        "post_refresh_age_seconds": pre_refresh_age_seconds,
    }
    try_last_mile_refresh = bool(row.get("observation_allowed_by_policy")) and policy_state == "OBSERVATION_POLICY_ELIGIBLE"
    if try_last_mile_refresh and not is_fresh_orderbook(orderbook, ttl_seconds=FRESH_ORDERBOOK_SECONDS):
        refresh_service = last_mile_orderbook_refresh or LastMileOrderbookRefreshService()
        last_mile_refresh_result = refresh_service.ensure_fresh(
            conn,
            decision_id=decision_id,
            source_review_id=review_id,
            market_id=market_id,
            condition_id=condition_id,
            token_id=token_id,
            side=side,
            ttl_seconds=FRESH_ORDERBOOK_SECONDS,
        )
        last_mile_refresh_result["attempted"] = True
        orderbook = latest_matching_orderbook(conn, market_id=market_id, token_id=token_id, side=side)

    if try_last_mile_refresh and not orderbook:
        blockers.append(str(last_mile_refresh_result.get("refresh_error") or "MISSING_FRESH_ORDERBOOK"))
    elif try_last_mile_refresh and not is_fresh_orderbook(orderbook, ttl_seconds=FRESH_ORDERBOOK_SECONDS):
        blockers.append(str(last_mile_refresh_result.get("refresh_error") or "STALE_ORDERBOOK"))

    market_key = (market_id, side)
    if market_id and side in {"YES", "NO"}:
        if market_key in seen_market_side:
            blockers.append("SAME_MARKET_DUPLICATE_DECISION")
        else:
            seen_market_side.add(market_key)
        active_session_id = active_paper_session_id(conn)
        if _open_position_count(conn, market_id=market_id, side=side, paper_session_id=active_session_id):
            blockers.append("DUPLICATE_OPEN_PAPER_EXPOSURE")
        if _fresh_active_intent_count(conn, market_id=market_id, side=side, paper_session_id=active_session_id):
            blockers.append("DUPLICATE_ACTIVE_PAPER_INTENT")

    blockers = _unique(blockers)
    warnings = _unique(warnings)
    defense_eval = apply_defense_to_blockers(blockers=blockers, warnings=warnings, score=score, profile=defense_profile)
    strict_blockers = _unique(defense_eval["strict_blockers"])
    blockers = _unique(defense_eval["effective_blockers"])
    warnings = _unique(defense_eval["warnings"])
    required = _required_to_pass(blockers)
    if defense_eval.get("fallback_exit"):
        required = [item for item in required if "Exit plan must" not in item]
    defense_learning_override = defense_profile.defense_level < 100 and (
        bool(defense_eval["ignored_blockers"])
        or bool(defense_eval["softened_blockers"])
        or bool(defense_eval["fallback_requirements"])
        or score >= defense_profile.adjusted_threshold
    )
    if not blockers and (policy_state == "OBSERVATION_POLICY_ELIGIBLE" or defense_learning_override):
        decision = "ENTER"
    elif policy_state == "OBSERVATION_POLICY_WATCH":
        decision = "WATCH"
    else:
        decision = "BLOCK"
    paper_enter_allowed = decision == "ENTER"
    orderbook_id = int(orderbook["id"]) if orderbook and "id" in orderbook else None
    post_refresh_age_seconds = orderbook_age_seconds(orderbook)
    post_orderbook_state = "FRESH" if is_fresh_orderbook(orderbook, ttl_seconds=FRESH_ORDERBOOK_SECONDS) else "STALE_OR_MISSING"
    evidence = {
        "source_layer": "paper_runtime_decision",
        "paper_runtime_decision_id": decision_id,
        "paper_observation_policy_review_id": review_id,
        "proactive_candidate_seed_id": row.get("proactive_candidate_seed_id"),
        "seed_mesh_inquiry_id": row.get("seed_mesh_inquiry_id"),
        "adapter_payload_id": row.get("adapter_payload_id"),
        "opportunity_score_id": row.get("opportunity_score_id"),
        "lineage": lineage,
        "paper_mode_policy": {
            "paper_enter_allowed": paper_enter_allowed,
            "live_enter_allowed": False,
            "full_paper_required": False,
            "paper_is_execution_adapter_only": True,
            "risk_state": risk_state,
            "capital_state": capital_state,
            "exit_state": exit_state,
            "lifecycle_state": lifecycle_state,
            "warnings": warnings,
            "blockers": blockers,
            "strict_blockers": strict_blockers,
            "defense_level": defense_profile.defense_level,
        },
        "paper_defense": {
            "defense_level": defense_profile.defense_level,
            "profile": defense_profile.to_dict(),
            "base_threshold": BASE_PAPER_THRESHOLD,
            "adjusted_threshold": defense_profile.adjusted_threshold,
            "observed_score": score,
            "strict_verdict": defense_eval["strict_verdict"],
            "effective_verdict": defense_eval["effective_verdict"],
            "strict_blockers": strict_blockers,
            "effective_blockers": blockers,
            "ignored_blockers": defense_eval["ignored_blockers"],
            "softened_blockers": defense_eval["softened_blockers"],
            "fallback_requirements": defense_eval["fallback_requirements"],
            "exit_plan_type": defense_eval["exit_plan_type"],
            "fallback_exit": defense_eval.get("fallback_exit"),
            "paper_only": True,
            "live_enter_allowed": False,
        },
        "orderbook_snapshot_text_id": orderbook.get("orderbook_snapshot_id") if orderbook else row.get("seed_orderbook_snapshot_id"),
        "orderbook_best_bid": _float(orderbook.get("best_bid")) if orderbook else None,
        "orderbook_best_ask": _float(orderbook.get("best_ask")) if orderbook else None,
        "orderbook_mid_price": _float(orderbook.get("mid_price")) if orderbook else None,
        "orderbook_spread": _float(orderbook.get("spread")) if orderbook else None,
        "orderbook_liquidity_score": _float(orderbook.get("liquidity_score")) if orderbook else None,
        "orderbook_age_seconds": post_refresh_age_seconds,
        "orderbook_ttl_seconds": FRESH_ORDERBOOK_SECONDS,
        "last_mile_orderbook_refresh": {
            "attempt_id": last_mile_refresh_result.get("attempt_id"),
            "attempted": bool(last_mile_refresh_result.get("attempted")),
            "refresh_state": last_mile_refresh_result.get("refresh_state") or last_mile_refresh_result.get("state"),
            "refresh_error": last_mile_refresh_result.get("refresh_error"),
            "pre_refresh_snapshot_id": last_mile_refresh_result.get("pre_refresh_snapshot_id"),
            "pre_refresh_age_seconds": last_mile_refresh_result.get("pre_refresh_age_seconds"),
            "post_refresh_snapshot_id": last_mile_refresh_result.get("post_refresh_snapshot_id") or orderbook_id,
            "post_refresh_age_seconds": last_mile_refresh_result.get("post_refresh_age_seconds") or post_refresh_age_seconds,
            "stale_cleared": bool(last_mile_refresh_result.get("stale_cleared")),
            "ttl_seconds": FRESH_ORDERBOOK_SECONDS,
        },
        "source_evidence": {
            "edge_state": edge_state,
            "thesis_state": thesis_state,
            "risk_state": risk_state,
            "capital_state": capital_state,
            "exit_state": exit_state,
            "lifecycle_state": lifecycle_state,
            "hard_blockers": hard,
            "soft_blockers": soft,
            "policy_blockers": policy_blockers,
            "observation_policy_state": policy_state,
            "direction_for_market": row.get("direction_for_market"),
            "direction_confidence": _float(row.get("direction_confidence")),
            "token_side_resolution_state": row.get("token_side_resolution_state"),
        },
        "side_evidence": {
            "direction_for_market": row.get("direction_for_market"),
            "direction_confidence": _float(row.get("direction_confidence")),
            "token_side_resolution_state": row.get("token_side_resolution_state"),
            "source": "proactive_candidate_seed" if row.get("direction_for_market") else "runtime_decision",
        },
        "diversity": {
            "selection_policy": "BEST_PER_MARKET_SIDE_THEN_DIVERSITY_RANK",
            "market_side_rank": market_side_rank,
            "duplicate_group_size": duplicate_group_size,
            "duplicate_suppressed_count": max(0, duplicate_group_size - 1),
            "diversity_score": _float(diversity_score),
            "trigger_type": row.get("trigger_type"),
            "seed_type": row.get("seed_type"),
            "seed_generation_source": row.get("seed_generation_source"),
            "priority_band": row.get("priority_band"),
            "priority_score": _float(row.get("priority_score")),
        },
    }
    return {
        "decision_id": decision_id,
        "source_type": "PROACTIVE_SEED_MESH",
        "candidate_source": "PROACTIVE_SEED_MESH",
        "source_review_id": review_id,
        "proactive_candidate_seed_id": row.get("proactive_candidate_seed_id"),
        "seed_mesh_inquiry_id": row.get("seed_mesh_inquiry_id"),
        "adapter_payload_id": row.get("adapter_payload_id"),
        "opportunity_score_id": row.get("opportunity_score_id"),
        "market_id": market_id,
        "condition_id": condition_id,
        "side": side,
        "token_id": token_id,
        "decision": decision,
        "decision_mode": "PAPER",
        "execution_mode": "PAPER",
        "paper_enter_allowed": paper_enter_allowed,
        "live_enter_allowed": False,
        "edge_state": edge_state,
        "thesis_state": thesis_state,
        "opportunity_score": score,
        "risk_state": risk_state,
        "capital_state": capital_state,
        "exit_state": exit_state,
        "lifecycle_state": lifecycle_state,
        "orderbook_state": orderbook_state,
        "orderbook_snapshot_id": orderbook_id,
        "orderbook_age_seconds": post_refresh_age_seconds,
        "orderbook_ttl_seconds": FRESH_ORDERBOOK_SECONDS,
        "last_mile_refresh_attempted": bool(last_mile_refresh_result.get("attempted")),
        "last_mile_refresh_state": last_mile_refresh_result.get("refresh_state") or last_mile_refresh_result.get("state"),
        "last_mile_refresh_error": last_mile_refresh_result.get("refresh_error"),
        "post_refresh_orderbook_state": post_orderbook_state,
        "token_verification_state": token_state,
        "candidate_event_scope_state": scope_state,
        "lineage_state": lineage_state,
        "research_lineage": lineage,
        "warnings_json": warnings,
        "blockers_json": blockers,
        "required_to_pass_json": required,
        "decision_batch_id": row.get("decision_batch_id"),
        "selection_rank": int(row.get("selection_rank") or 0),
        "market_side_rank": market_side_rank,
        "diversity_score": diversity_score,
        "duplicate_suppressed_count": max(0, duplicate_group_size - 1),
        "is_current_batch": True,
        "policy_json": {
            "observation_policy_state": policy_state,
            "paper_mode_minimum_truth": True,
            "full_paper_required": False,
            "capital_watch_allowed_with_warning": True,
            "risk_review_allowed_with_warning": True,
            "data_only_research_allowed_paper_adapter_only": True,
            "paper_defense_level": defense_profile.defense_level,
            "base_paper_threshold": BASE_PAPER_THRESHOLD,
            "adjusted_paper_threshold": defense_profile.adjusted_threshold,
            "strict_verdict": defense_eval["strict_verdict"],
            "effective_verdict": defense_eval["effective_verdict"],
            "ignored_blockers": defense_eval["ignored_blockers"],
            "softened_blockers": defense_eval["softened_blockers"],
            "fallback_requirements": defense_eval["fallback_requirements"],
            "live_enter_allowed": False,
        },
        "evidence": evidence,
        "generated_by": "paper_runtime_decision_service",
    }


def _arbitrate_same_market_opposing_enters(decisions: list[dict[str, Any]], conn: Any | None = None) -> list[dict[str, Any]]:
    """Resolve same-market YES/NO ENTER conflicts before PaperIntentGate."""

    return SameMarketSideArbitrator().arbitrate(decisions, conn=conn)


def _demote_opposing_enter(
    decision: dict[str, Any],
    *,
    blocker: str,
    required: str,
    state: str,
    winner_side: str | None,
) -> None:
    blockers = _unique([*_list(decision.get("blockers_json")), blocker])
    required_to_pass = _unique([*_list(decision.get("required_to_pass_json")), required])
    warnings = _unique([*_list(decision.get("warnings_json")), "PAPER_BATCH_OPPOSING_SIDE_ARBITRATED"])
    decision["decision"] = "BLOCK"
    decision["paper_enter_allowed"] = False
    decision["blockers_json"] = blockers
    decision["required_to_pass_json"] = required_to_pass
    decision["warnings_json"] = warnings
    policy = _dict(decision.get("policy_json"))
    policy["opposing_side_arbitration"] = state
    policy["paper_enter_allowed"] = False
    decision["policy_json"] = policy
    _append_evidence_arbitration(
        decision,
        market_id=str(decision.get("market_id") or ""),
        state=state,
        winner_side=winner_side,
    )


def _append_evidence_arbitration(
    decision: dict[str, Any],
    *,
    market_id: str,
    state: str,
    winner_side: str | None,
) -> None:
    evidence = _dict(decision.get("evidence"))
    evidence["same_market_opposing_enter_arbitration"] = {
        "market_id": market_id,
        "state": state,
        "winner_side": winner_side,
        "score": _float(decision.get("opportunity_score")),
        "source": "paper_runtime_decision_service",
    }
    decision["evidence"] = evidence


def _candidate_rows(conn: Any, *, limit: int, force: bool) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_observation_policy_reviews"):
        return []
    recent_filter = "" if force else """
        AND NOT EXISTS (
            SELECT 1
            FROM paper_runtime_decisions prd
            WHERE prd.source_review_id=popr.paper_observation_policy_review_id
              AND prd.updated_at >= now() - interval '10 minutes'
              AND NOT (
                  prd.blockers_json ? 'STALE_ORDERBOOK'
                  OR prd.blockers_json ? 'MISSING_FRESH_ORDERBOOK'
                  OR prd.blockers_json ? 'ORDERBOOK_REFRESH_FAILED'
                  OR prd.blockers_json ? 'ORDERBOOK_CONNECTOR_ERROR'
                  OR prd.blockers_json ? 'ORDERBOOK_TTL_EXPIRED_AFTER_REFRESH'
              )
        )
    """
    rows = conn.execute(
        f"""
        WITH base AS (
        SELECT
            popr.*,
            pcs.orderbook_snapshot_id AS seed_orderbook_snapshot_id,
            pcs.direction_for_market,
            pcs.direction_confidence,
            pcs.token_side_resolution_state,
            pcs.seed_type,
            pcs.trigger_type,
            pcs.seed_generation_source,
            psr.seed_mesh_result_id,
            psr.metadata_json AS mesh_result_metadata,
            COALESCE(rpw.priority_band, 'LOW') AS priority_band,
            COALESCE(rpw.priority_score, 0) AS priority_score
        FROM paper_observation_policy_reviews popr
        LEFT JOIN proactive_candidate_seeds pcs
            ON pcs.proactive_candidate_seed_id=popr.proactive_candidate_seed_id
        LEFT JOIN proactive_seed_mesh_results psr
            ON psr.seed_mesh_inquiry_id=popr.seed_mesh_inquiry_id
        LEFT JOIN research_priority_watchlist rpw
            ON rpw.market_id=popr.market_id
        WHERE popr.observation_policy_state IN (
              'OBSERVATION_POLICY_ELIGIBLE',
              'OBSERVATION_POLICY_WATCH',
              'OBSERVATION_POLICY_BLOCKED',
              'OBSERVATION_POLICY_INCOMPLETE'
          )
          AND COALESCE(popr.execution_allowed, false) IS FALSE
          AND COALESCE(popr.paper_allowed, false) IS FALSE
          AND COALESCE(popr.shadow_allowed, false) IS FALSE
          AND COALESCE(popr.live_allowed, false) IS FALSE
          {recent_filter}
        ), ranked AS (
            SELECT
                base.*,
                ROW_NUMBER() OVER (
                    PARTITION BY base.market_id, base.side
                    ORDER BY base.opportunity_score DESC, base.updated_at DESC, base.id DESC
                ) AS market_side_rank,
                COUNT(*) OVER (PARTITION BY base.market_id, base.side) AS duplicate_group_size,
                (
                    COALESCE(base.opportunity_score, 0)
                    + CASE base.observation_policy_state
                        WHEN 'OBSERVATION_POLICY_ELIGIBLE' THEN 100
                        WHEN 'OBSERVATION_POLICY_WATCH' THEN 40
                        WHEN 'OBSERVATION_POLICY_INCOMPLETE' THEN 10
                        ELSE 0
                      END
                    + CASE COALESCE(base.priority_band, 'LOW')
                        WHEN 'HIGH' THEN 15
                        WHEN 'MEDIUM' THEN 8
                        WHEN 'LOW' THEN 3
                        ELSE 0
                      END
                    + LEAST(COALESCE(base.priority_score, 0) / 10.0, 10)
                    + CASE WHEN base.trigger_type IS NOT NULL THEN 2 ELSE 0 END
                    + CASE WHEN base.side='NO' THEN 1 ELSE 0 END
                ) AS diversity_score
            FROM base
        ), selected AS (
            SELECT
                ranked.*,
                ROW_NUMBER() OVER (
                    ORDER BY ranked.diversity_score DESC, ranked.opportunity_score DESC, ranked.updated_at DESC, ranked.id DESC
                ) AS selection_rank
            FROM ranked
            WHERE market_side_rank = 1
        )
        SELECT selected.*, %s AS decision_batch_id
        FROM selected
        ORDER BY selection_rank
        LIMIT %s
        """,
        (f"paper_runtime_batch_{uuid4().hex}", limit),
    ).fetchall()
    return [_json_safe(dict(row)) for row in rows]


def _decision_as_gate_candidate(row: dict[str, Any]) -> dict[str, Any]:
    evidence = _dict(row.get("evidence"))
    paper_defense = _dict(evidence.get("paper_defense"))
    score = _decimal(row.get("opportunity_score"))
    decision_id = str(row["decision_id"])
    thesis_id = _text(_nested(evidence, "source_evidence", "trade_thesis_id")) or f"paper_runtime_thesis_{decision_id}"
    risk_id = _text(_nested(evidence, "source_evidence", "risk_evidence_id")) or f"paper_runtime_risk_{decision_id}"
    exit_plan_id = _text(_nested(evidence, "source_evidence", "exit_plan_id")) or f"paper_runtime_exit_{decision_id}"
    return {
        "id": row.get("id"),
        "eligibility_id": decision_id,
        "candidate_id": decision_id,
        "paper_runtime_decision_id": decision_id,
        "source_layer": "paper_runtime_decision",
        "candidate_source": row.get("candidate_source"),
        "thesis_id": thesis_id,
        "risk_decision_id": risk_id,
        "exit_plan_id": exit_plan_id,
        "coordinator_decision_id": row.get("seed_mesh_inquiry_id"),
        "market_id": row.get("market_id"),
        "condition_id": row.get("condition_id"),
        "side": row.get("side"),
        "token_id": row.get("token_id"),
        "status": "ELIGIBLE" if row.get("paper_enter_allowed") else "BLOCKED",
        "eligibility_score": float(max(Decimal("0"), min(Decimal("1"), score / Decimal("100")))),
        "eligibility_blockers": _list(row.get("blockers_json")),
        "missing_requirements": _list(row.get("required_to_pass_json")),
        "evidence": {
            **evidence,
            "paper_runtime_decision": _json_safe(row),
            "paper_runtime_decision_id": decision_id,
            "paper_enter_allowed": bool(row.get("paper_enter_allowed")),
            "intended_notional": _float(Decimal("1000") * _decimal(_nested(paper_defense, "profile", "max_single_trade_pct") or 2) / Decimal("100")),
        },
        "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
        "link_confidence": None,
        "lineage_trusted": str(row.get("lineage_state") or "").upper() == "COMPLETE",
        "risk_approved": str(row.get("risk_state") or "").upper() not in RISK_BLOCK_STATES,
        "exit_ready": str(row.get("exit_state") or "").upper() in EXIT_READY_STATES or paper_defense.get("exit_plan_type") == "FALLBACK_LEARNING",
        "not_dry_run": True,
        "paper_intent_allowed": False,
        "execution_allowed": False,
        "generated_by": "runtime",
        "producer_name": "paper_runtime_decision_service",
        "is_runtime_generated": True,
        "is_dry_run_generated": False,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _ensure_tables(conn: Any) -> None:
    ensure_last_mile_orderbook_tables(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_runtime_decisions (
            id BIGSERIAL PRIMARY KEY,
            decision_id TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL DEFAULT 'PROACTIVE_SEED_MESH',
            candidate_source TEXT NOT NULL DEFAULT 'PROACTIVE_SEED_MESH',
            source_review_id TEXT,
            proactive_candidate_seed_id TEXT,
            seed_mesh_inquiry_id TEXT,
            adapter_payload_id TEXT,
            opportunity_score_id TEXT,
            market_id TEXT,
            condition_id TEXT,
            side TEXT,
            token_id TEXT,
            decision TEXT NOT NULL,
            decision_mode TEXT NOT NULL DEFAULT 'PAPER',
            execution_mode TEXT NOT NULL DEFAULT 'PAPER',
            paper_enter_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            live_enter_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            edge_state TEXT,
            thesis_state TEXT,
            opportunity_score NUMERIC NOT NULL DEFAULT 0,
            risk_state TEXT,
            capital_state TEXT,
            exit_state TEXT,
            lifecycle_state TEXT,
            orderbook_state TEXT,
            orderbook_snapshot_id BIGINT,
            orderbook_age_seconds NUMERIC,
            orderbook_ttl_seconds INTEGER NOT NULL DEFAULT 180,
            last_mile_refresh_attempted BOOLEAN NOT NULL DEFAULT FALSE,
            last_mile_refresh_state TEXT,
            last_mile_refresh_error TEXT,
            post_refresh_orderbook_state TEXT,
            token_verification_state TEXT,
            candidate_event_scope_state TEXT,
            lineage_state TEXT,
            research_lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
            warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            decision_batch_id TEXT,
            selection_rank INTEGER NOT NULL DEFAULT 0,
            market_side_rank INTEGER NOT NULL DEFAULT 1,
            diversity_score NUMERIC NOT NULL DEFAULT 0,
            duplicate_suppressed_count INTEGER NOT NULL DEFAULT 0,
            is_current_batch BOOLEAN NOT NULL DEFAULT true,
            policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            generated_by TEXT NOT NULL DEFAULT 'paper_runtime_decision_service',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    for ddl in (
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS decision_batch_id TEXT",
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS selection_rank INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS market_side_rank INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS diversity_score NUMERIC NOT NULL DEFAULT 0",
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS duplicate_suppressed_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS is_current_batch BOOLEAN NOT NULL DEFAULT true",
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS orderbook_age_seconds NUMERIC",
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS orderbook_ttl_seconds INTEGER NOT NULL DEFAULT 180",
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS last_mile_refresh_attempted BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS last_mile_refresh_state TEXT",
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS last_mile_refresh_error TEXT",
        "ALTER TABLE paper_runtime_decisions ADD COLUMN IF NOT EXISTS post_refresh_orderbook_state TEXT",
    ):
        conn.execute(ddl)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_runtime_decision_runs (
            id BIGSERIAL PRIMARY KEY,
            run_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            candidates_reviewed INTEGER NOT NULL DEFAULT 0,
            enter_count INTEGER NOT NULL DEFAULT 0,
            watch_count INTEGER NOT NULL DEFAULT 0,
            blocked_count INTEGER NOT NULL DEFAULT 0,
            latest_error TEXT,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def _upsert_decision(conn: Any, decision: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO paper_runtime_decisions (
            decision_id, source_type, candidate_source, source_review_id,
            proactive_candidate_seed_id, seed_mesh_inquiry_id, adapter_payload_id,
            opportunity_score_id, market_id, condition_id, side, token_id,
            decision, decision_mode, execution_mode, paper_enter_allowed,
            live_enter_allowed, edge_state, thesis_state, opportunity_score,
            risk_state, capital_state, exit_state, lifecycle_state,
            orderbook_state, orderbook_snapshot_id, orderbook_age_seconds,
            orderbook_ttl_seconds, last_mile_refresh_attempted,
            last_mile_refresh_state, last_mile_refresh_error,
            post_refresh_orderbook_state, token_verification_state,
            candidate_event_scope_state, lineage_state, research_lineage,
            warnings_json, blockers_json, required_to_pass_json,
            decision_batch_id, selection_rank, market_side_rank,
            diversity_score, duplicate_suppressed_count, is_current_batch,
            policy_json,
            evidence, generated_by
        )
        VALUES (
            %(decision_id)s, %(source_type)s, %(candidate_source)s, %(source_review_id)s,
            %(proactive_candidate_seed_id)s, %(seed_mesh_inquiry_id)s, %(adapter_payload_id)s,
            %(opportunity_score_id)s, %(market_id)s, %(condition_id)s, %(side)s, %(token_id)s,
            %(decision)s, %(decision_mode)s, %(execution_mode)s, %(paper_enter_allowed)s,
            %(live_enter_allowed)s, %(edge_state)s, %(thesis_state)s, %(opportunity_score)s,
            %(risk_state)s, %(capital_state)s, %(exit_state)s, %(lifecycle_state)s,
            %(orderbook_state)s, %(orderbook_snapshot_id)s, %(orderbook_age_seconds)s,
            %(orderbook_ttl_seconds)s, %(last_mile_refresh_attempted)s,
            %(last_mile_refresh_state)s, %(last_mile_refresh_error)s,
            %(post_refresh_orderbook_state)s, %(token_verification_state)s,
            %(candidate_event_scope_state)s, %(lineage_state)s, %(research_lineage)s,
            %(warnings_json)s, %(blockers_json)s, %(required_to_pass_json)s,
            %(decision_batch_id)s, %(selection_rank)s, %(market_side_rank)s,
            %(diversity_score)s, %(duplicate_suppressed_count)s, %(is_current_batch)s,
            %(policy_json)s,
            %(evidence)s, %(generated_by)s
        )
        ON CONFLICT (decision_id) DO UPDATE SET
            source_type=EXCLUDED.source_type,
            candidate_source=EXCLUDED.candidate_source,
            source_review_id=EXCLUDED.source_review_id,
            proactive_candidate_seed_id=EXCLUDED.proactive_candidate_seed_id,
            seed_mesh_inquiry_id=EXCLUDED.seed_mesh_inquiry_id,
            adapter_payload_id=EXCLUDED.adapter_payload_id,
            opportunity_score_id=EXCLUDED.opportunity_score_id,
            market_id=EXCLUDED.market_id,
            condition_id=EXCLUDED.condition_id,
            side=EXCLUDED.side,
            token_id=EXCLUDED.token_id,
            decision=EXCLUDED.decision,
            decision_mode=EXCLUDED.decision_mode,
            execution_mode=EXCLUDED.execution_mode,
            paper_enter_allowed=EXCLUDED.paper_enter_allowed,
            live_enter_allowed=FALSE,
            edge_state=EXCLUDED.edge_state,
            thesis_state=EXCLUDED.thesis_state,
            opportunity_score=EXCLUDED.opportunity_score,
            risk_state=EXCLUDED.risk_state,
            capital_state=EXCLUDED.capital_state,
            exit_state=EXCLUDED.exit_state,
            lifecycle_state=EXCLUDED.lifecycle_state,
            orderbook_state=EXCLUDED.orderbook_state,
            orderbook_snapshot_id=EXCLUDED.orderbook_snapshot_id,
            orderbook_age_seconds=EXCLUDED.orderbook_age_seconds,
            orderbook_ttl_seconds=EXCLUDED.orderbook_ttl_seconds,
            last_mile_refresh_attempted=EXCLUDED.last_mile_refresh_attempted,
            last_mile_refresh_state=EXCLUDED.last_mile_refresh_state,
            last_mile_refresh_error=EXCLUDED.last_mile_refresh_error,
            post_refresh_orderbook_state=EXCLUDED.post_refresh_orderbook_state,
            token_verification_state=EXCLUDED.token_verification_state,
            candidate_event_scope_state=EXCLUDED.candidate_event_scope_state,
            lineage_state=EXCLUDED.lineage_state,
            research_lineage=EXCLUDED.research_lineage,
            warnings_json=EXCLUDED.warnings_json,
            blockers_json=EXCLUDED.blockers_json,
            required_to_pass_json=EXCLUDED.required_to_pass_json,
            decision_batch_id=EXCLUDED.decision_batch_id,
            selection_rank=EXCLUDED.selection_rank,
            market_side_rank=EXCLUDED.market_side_rank,
            diversity_score=EXCLUDED.diversity_score,
            duplicate_suppressed_count=EXCLUDED.duplicate_suppressed_count,
            is_current_batch=EXCLUDED.is_current_batch,
            policy_json=EXCLUDED.policy_json,
            evidence=EXCLUDED.evidence,
            generated_by=EXCLUDED.generated_by,
            updated_at=now()
        """,
        _sql_params(decision),
    )


def _insert_run(
    conn: Any,
    *,
    run_id: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    latest_error: str | None,
    metadata: dict[str, Any],
    **stats: Any,
) -> None:
    conn.execute(
        """
        INSERT INTO paper_runtime_decision_runs (
            run_id, status, started_at, finished_at, candidates_reviewed,
            enter_count, watch_count, blocked_count, latest_error, metadata_json
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (run_id) DO UPDATE SET
            status=EXCLUDED.status,
            finished_at=EXCLUDED.finished_at,
            metadata_json=EXCLUDED.metadata_json,
            updated_at=now()
        """,
        (
            run_id,
            status,
            started_at,
            finished_at,
            int(stats.get("candidates_reviewed") or 0),
            int(stats.get("enter_count") or 0),
            int(stats.get("watch_count") or 0),
            int(stats.get("block_count") or stats.get("blocked_count") or 0),
            latest_error,
            Jsonb(_json_safe(metadata)),
        ),
    )


def _latest_fresh_orderbook(conn: Any, *, market_id: str | None, token_id: str | None, side: str | None) -> dict[str, Any] | None:
    if not market_id or not _table_exists(conn, "orderbook_snapshots"):
        return None
    row = conn.execute(
        """
        SELECT *
        FROM orderbook_snapshots
        WHERE market_id=%s
          AND COALESCE(is_stale, false) IS FALSE
          AND snapshot_status IN ('OK','PARTIAL')
          AND (
              %s::text IS NULL
              OR token_id=%s
              OR side=%s
          )
        ORDER BY
          CASE WHEN token_id=%s THEN 0 WHEN side=%s THEN 1 ELSE 2 END,
          COALESCE(snapshot_at, collected_at, created_at) DESC,
          id DESC
        LIMIT 1
        """,
        (market_id, token_id, token_id, side, token_id, side),
    ).fetchone()
    return dict(row) if row else None


def _orderbook_age_seconds(row: dict[str, Any]) -> float:
    ts = row.get("snapshot_at") or row.get("collected_at") or row.get("created_at")
    if ts is None:
        return float("inf")
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return float("inf")
    if not isinstance(ts, datetime):
        return float("inf")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - ts.astimezone(UTC)).total_seconds())


def _open_position_count(conn: Any, *, market_id: str, side: str, paper_session_id: str | None = None) -> int:
    if not _table_exists(conn, "paper_positions"):
        return 0
    session_clause = "AND (%s::text IS NULL OR paper_session_id = %s::text)" if _column_exists(conn, "paper_positions", "paper_session_id") else "AND %s::text IS NULL AND %s::text IS NULL"
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM paper_positions
        WHERE market_id=%s
          AND intended_outcome=%s
          AND current_status IN ('OPEN','ACTIVE')
          AND closed_at IS NULL
          {session_clause}
        """,
        (market_id, side, paper_session_id, paper_session_id),
    ).fetchone()
    return int((row or {}).get("count") or 0)


def _fresh_active_intent_count(conn: Any, *, market_id: str, side: str, paper_session_id: str | None = None) -> int:
    if not _table_exists(conn, "paper_intents"):
        return 0
    session_clause = "AND (%s::text IS NULL OR paper_session_id = %s::text)" if _column_exists(conn, "paper_intents", "paper_session_id") else "AND %s::text IS NULL AND %s::text IS NULL"
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM paper_intents
        WHERE market_id=%s
          AND side=%s
          AND intent_status IN ('CREATED','READY','EXECUTING')
          AND created_at >= now() - interval '10 minutes'
          {session_clause}
        """,
        (market_id, side, paper_session_id, paper_session_id),
    ).fetchone()
    return int((row or {}).get("count") or 0)


def _required_to_pass(blockers: list[str]) -> list[str]:
    mapping = {
        "MISSING_FRESH_ORDERBOOK": "Refresh the market orderbook before PAPER entry.",
        "STALE_ORDERBOOK": "Refresh the market orderbook within the paper execution freshness TTL.",
        "ORDERBOOK_REFRESH_FAILED": "Retry targeted orderbook refresh and verify connector response.",
        "ORDERBOOK_CONNECTOR_ERROR": "Restore read-only CLOB orderbook connector access.",
        "ORDERBOOK_TOKEN_MISMATCH": "Verify candidate token id matches the refreshed orderbook asset id.",
        "ORDERBOOK_MARKET_MISMATCH": "Verify candidate market/condition matches refreshed orderbook market.",
        "ORDERBOOK_EMPTY": "Orderbook must contain bid and ask levels before PAPER entry.",
        "ORDERBOOK_TTL_EXPIRED_AFTER_REFRESH": "Refresh produced a snapshot outside the PAPER freshness TTL.",
        "SAME_MARKET_DUPLICATE_DECISION": "Deduplicate repeated source events for the same market and side.",
        "DUPLICATE_OPEN_PAPER_EXPOSURE": "Close or explicitly permit duplicate open paper exposure before another entry.",
        "DUPLICATE_ACTIVE_PAPER_INTENT": "Consume or expire the active same-market same-side paper intent.",
        "RISK_HARD_BLOCKED": "Risk hard blocker must clear.",
        "CAPITAL_HARD_BLOCKED": "Capital hard blocker must clear.",
        "EXIT_NOT_READY": "Exit/time-stop/invalidation plan must be ready.",
        "TOKEN_SIDE_NOT_VERIFIED": "Token and side must be verified.",
        "LINEAGE_NOT_COMPLETE": "Research lineage must be complete.",
    }
    return [mapping[item] for item in blockers if item in mapping]


def _decision_id(value: str) -> str:
    return "paper_runtime_decision_" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:32]


def _sql_params(decision: dict[str, Any]) -> dict[str, Any]:
    params = dict(decision)
    for key in ("research_lineage", "warnings_json", "blockers_json", "required_to_pass_json", "policy_json", "evidence"):
        params[key] = Jsonb(_json_safe(params.get(key) or ([] if key.endswith("_json") else {})))
    return params


def _safety_counts(conn: Any) -> dict[str, int]:
    return {
        "paper_intents": _count_table(conn, "paper_intents"),
        "paper_orders": _count_table(conn, "paper_orders"),
        "paper_fills": _count_table(conn, "paper_fills"),
        "paper_positions": _count_table(conn, "paper_positions"),
        "live_orders": _count_table(conn, "live_orders"),
        "shadow_orders": _count_table(conn, "shadow_orders"),
        "orders_v2": _count_table(conn, "orders_v2"),
    }


def _trading_mutation(before: dict[str, int], after: dict[str, int]) -> bool:
    return any(after.get(key, 0) > before.get(key, 0) for key in before)


def _latest_run(conn: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_runtime_decision_runs"):
        return None
    row = conn.execute("SELECT * FROM paper_runtime_decision_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _json_array_counts(conn: Any, column: str, *, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_runtime_decisions"):
        return []
    rows = conn.execute(
        f"""
        SELECT value AS blocker, COUNT(*) AS count
        FROM paper_runtime_decisions,
             LATERAL jsonb_array_elements_text({column}) AS value
        GROUP BY value
        ORDER BY count DESC, blocker
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_json_safe(dict(row)) for row in rows]


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return bool(row)


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip().upper()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _text(value: Any) -> str | None:
    text = str(value).strip() if value not in (None, "") else ""
    return text or None


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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
