from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_session import active_paper_session_id
from app.utils.json_safety import json_safe

BASE_PAPER_THRESHOLD = Decimal("60")
DEFAULT_DEFENSE_LEVEL = 100


@dataclass(frozen=True)
class PaperDefenseProfile:
    defense_level: int
    base_threshold: Decimal
    adjusted_threshold: Decimal
    max_deployed_pct: Decimal
    max_single_trade_pct: Decimal
    max_open_positions: int
    min_cash_reserve_pct: Decimal
    exit_fallback_enabled: bool
    strategic_blocker_mode: str
    integrity_blocker_mode: str = "HARD"

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class BlockerPolicy:
    blocker_code: str
    owner_gate: str
    category: str
    base_type: str
    can_soften: bool
    can_ignore_in_paper: bool
    never_ignore: bool
    required_defense_to_block: int
    learning_report_label: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


INTEGRITY_BLOCKERS = {
    "INVALID_MARKET",
    "MISSING_MARKET_ID",
    "MISSING_TOKEN_ID",
    "INVALID_SIDE",
    "MISSING_SIDE",
    "TOKEN_SIDE_NOT_VERIFIED",
    "MARKET_CLOSED",
    "MARKET_NOT_ACCEPTING_ORDERS",
    "NO_ACTIVE_PAPER_SESSION",
    "MISSING_EXECUTABLE_PRICE",
    "MISSING_QUANTITY",
    "INVALID_NOTIONAL",
    "PAPER_ACCOUNT_MISSING",
    "INSUFFICIENT_PAPER_BALANCE",
    "DB_WRITE_FAILURE",
    "SOURCE_REVIEW_EXECUTION_FLAG_TRUE",
    "LIVE_ACTION_FORBIDDEN",
    "SHADOW_ACTION_FORBIDDEN",
    "REAL_ORDER_FORBIDDEN",
    "DUPLICATE_OPEN_PAPER_EXPOSURE",
    "DUPLICATE_ACTIVE_PAPER_INTENT",
    "SAME_MARKET_DUPLICATE_DECISION",
    "SAME_MARKET_OPPOSING_ENTER_CONFLICT",
    "SAME_MARKET_OPPOSING_SIDE_BLOCK",
    "SAME_MARKET_OPPOSING_SIDE_LOST_ARBITRATION",
    "OPPOSING_SIDE_DEMOTED_BY_ARBITRATION",
    "SAME_MARKET_OPPOSING_SIDE_UNRESOLVED",
    "INTEGRITY_BLOCKER_PREVENTED_ARBITRATION",
}

EXECUTION_VALIDITY_BLOCKERS = {
    "ORDERBOOK_NOT_FRESH",
    "STALE_ORDERBOOK",
    "MISSING_FRESH_ORDERBOOK",
    "MISSING_TRUSTED_ORDERBOOK",
    "ORDERBOOK_REFRESH_FAILED",
    "ORDERBOOK_CONNECTOR_ERROR",
    "ORDERBOOK_TTL_EXPIRED_AFTER_REFRESH",
    "ORDERBOOK_TOO_WIDE",
    "ORDERBOOK_EMPTY",
    "ORDERBOOK_LIQUIDITY_UNKNOWN",
    "NO_EXECUTABLE_PAPER_PRICE",
    "NO_BOUNDED_PAPER_PRICE",
}

EXIT_BLOCKERS = {
    "EXIT_NOT_READY",
    "MISSING_DYNAMIC_HOLD_TIME",
    "MISSING_EXIT_PLAN",
    "EXIT_PLAN_MISSING",
}

STRATEGIC_BLOCKERS = {
    "OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD",
    "EXISTING_HARD_BLOCKERS_PRESENT",
    "THESIS_NOT_SUPPORTED",
    "EDGE_NOT_SUPPORTED",
    "DECISION_BAND_NOT_PAPER_OBSERVATION",
    "OBSERVATION_POLICY_NOT_ALLOWED",
    "CANDIDATE_EVENT_SCOPE_NOT_SCOPED",
    "LINEAGE_NOT_COMPLETE",
    "CAPITAL_HARD_BLOCKED",
    "CAPITAL_SUPPORT_REQUIRED",
    "RISK_REVIEW",
    "AI_UNCERTAINTY",
}

BLOCKER_POLICY_MAP: dict[str, BlockerPolicy] = {
    **{
        code: BlockerPolicy(
            blocker_code=code,
            owner_gate="SystemIntegrity",
            category="SYSTEM_INTEGRITY",
            base_type="INTEGRITY",
            can_soften=False,
            can_ignore_in_paper=False,
            never_ignore=True,
            required_defense_to_block=0,
            learning_report_label="integrity_required",
            explanation="This blocker protects valid market identity, accounting, or execution integrity and remains hard at every PAPER defense level.",
        )
        for code in INTEGRITY_BLOCKERS
    },
    **{
        code: BlockerPolicy(
            blocker_code=code,
            owner_gate="ExecutionValidity",
            category="EXECUTION_VALIDITY",
            base_type="HARD",
            can_soften=False,
            can_ignore_in_paper=False,
            never_ignore=True,
            required_defense_to_block=0,
            learning_report_label="execution_validity_required",
            explanation="This blocker requires fresh usable simulated execution evidence before a PAPER entry.",
        )
        for code in EXECUTION_VALIDITY_BLOCKERS
    },
    **{
        code: BlockerPolicy(
            blocker_code=code,
            owner_gate="ExitMesh",
            category="EXIT_REQUIREMENT",
            base_type="HARD",
            can_soften=True,
            can_ignore_in_paper=False,
            never_ignore=False,
            required_defense_to_block=60,
            learning_report_label="fallback_exit_required",
            explanation="This blocker can be converted to a PAPER learning fallback exit at low defense, but only if fallback exit metadata is recorded.",
        )
        for code in EXIT_BLOCKERS
    },
    **{
        code: BlockerPolicy(
            blocker_code=code,
            owner_gate="PaperRuntimeDecision",
            category="STRATEGIC_PROTECTION",
            base_type="HARD",
            can_soften=True,
            can_ignore_in_paper=True,
            never_ignore=False,
            required_defense_to_block=40,
            learning_report_label="strategic_learning_warning",
            explanation="This is a strategic protection that can become a PAPER learning warning at low defense.",
        )
        for code in STRATEGIC_BLOCKERS
    },
}


class PaperDefenseGovernor:
    """PAPER-only global protection dial.

    It changes only PAPER effective decisions. It never enables live/shadow/real
    actions and never marks integrity blockers safe.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, report_root: Path | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._report_root = report_root or Path("run_reports")

    def status(self) -> dict[str, Any]:
        if not self._factory.enabled:
            profile = defense_profile(DEFAULT_DEFENSE_LEVEL)
            return {
                "status": "DATABASE_UNAVAILABLE",
                "active_session_id": None,
                "defense_level": profile.defense_level,
                "defense_profile": profile.to_dict(),
                "blocker_policy_summary": blocker_policy_summary(),
            }
        with self._factory.connect() as conn:
            return paper_defense_status(conn)

    def set_defense_level(self, *, defense_level: int, reason: str = "manual PAPER defense update", actor: str = "polybot-api") -> dict[str, Any]:
        level = normalize_defense_level(defense_level)
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "errors": ["POLYBOT_DATABASE_URL is not configured"]}
        with self._factory.connect() as conn, conn.transaction():
            ensure_runtime_tables(conn)
            session_id = active_paper_session_id(conn)
            if not session_id:
                return {"status": "REJECTED", "errors": ["NO_ACTIVE_PAPER_SESSION"]}
            old_row = conn.execute("SELECT defense_level FROM paper_sessions WHERE paper_session_id=%s FOR UPDATE", (session_id,)).fetchone()
            old_level = int((old_row or {}).get("defense_level") or DEFAULT_DEFENSE_LEVEL)
            profile = defense_profile(level)
            conn.execute(
                """
                UPDATE paper_sessions
                SET defense_level=%s,
                    defense_profile_snapshot=%s,
                    max_deployed_pct=%s,
                    max_single_trade_pct=%s,
                    metadata_json=COALESCE(metadata_json,'{}'::jsonb) || %s,
                    updated_at=now()
                WHERE paper_session_id=%s
                """,
                (
                    level,
                    Jsonb(profile.to_dict()),
                    profile.max_deployed_pct,
                    profile.max_single_trade_pct,
                    Jsonb({"paper_defense_level": level, "paper_defense_updated_at": datetime.now(UTC).isoformat()}),
                    session_id,
                ),
            )
            apply_profile_to_paper_account(conn, session_id=session_id, profile=profile)
            event_id = f"paper_defense_event_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
            conn.execute(
                """
                INSERT INTO paper_defense_events (
                    event_id, paper_session_id, old_defense_level, new_defense_level,
                    reason, actor, metadata_json
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (event_id, session_id, old_level, level, reason, actor, Jsonb({"profile": profile.to_dict(), "paper_only": True})),
            )
            return {"status": "OK", "event_id": event_id, "paper_session_id": session_id, "old_defense_level": old_level, "new_defense_level": level, "defense_profile": profile.to_dict()}

    def learning_report(self, *, session_id: str | None = None, write_files: bool = True) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "errors": ["POLYBOT_DATABASE_URL is not configured"]}
        with self._factory.connect() as conn:
            ensure_runtime_tables(conn)
            target_session = session_id or active_paper_session_id(conn)
            if not target_session:
                return {"status": "NO_ACTIVE_PAPER_SESSION", "session_id": None}
            report = build_learning_report(conn, target_session)
            if write_files:
                paths = write_learning_report_files(report, self._report_root)
                report["report_paths"] = paths
                conn.execute(
                    "UPDATE paper_sessions SET session_learning_report_path=%s, updated_at=now() WHERE paper_session_id=%s",
                    (paths.get("json"), target_session),
                )
                conn.commit()
            return json_safe(report)


def normalize_defense_level(value: Any) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        level = DEFAULT_DEFENSE_LEVEL
    return max(0, min(100, level))


def defense_profile(level: int | str | None) -> PaperDefenseProfile:
    level = normalize_defense_level(level)
    if level >= 100:
        threshold = Decimal("60")
        max_deployed = Decimal("20")
        max_single = Decimal("2")
        max_open = 2
        reserve = Decimal("80")
    elif level >= 80:
        threshold = Decimal("57")
        max_deployed = Decimal("35")
        max_single = Decimal("3")
        max_open = 3
        reserve = Decimal("65")
    elif level >= 60:
        threshold = Decimal("53")
        max_deployed = Decimal("50")
        max_single = Decimal("5")
        max_open = 5
        reserve = Decimal("50")
    elif level >= 40:
        threshold = Decimal("48")
        max_deployed = Decimal("70")
        max_single = Decimal("10")
        max_open = 10
        reserve = Decimal("30")
    elif level >= 20:
        threshold = Decimal("42")
        max_deployed = Decimal("80")
        max_single = Decimal("15")
        max_open = 15
        reserve = Decimal("20")
    else:
        threshold = Decimal("30")
        max_deployed = Decimal("95")
        max_single = Decimal("20")
        max_open = 25
        reserve = Decimal("5")
    return PaperDefenseProfile(
        defense_level=level,
        base_threshold=BASE_PAPER_THRESHOLD,
        adjusted_threshold=threshold,
        max_deployed_pct=max_deployed,
        max_single_trade_pct=max_single,
        max_open_positions=max_open,
        min_cash_reserve_pct=reserve,
        exit_fallback_enabled=level <= 40,
        strategic_blocker_mode="HARD" if level >= 100 else "MIXED" if level >= 60 else "WARNING_ONLY" if level >= 20 else "IGNORED_FOR_LEARNING",
    )


def paper_defense_status(conn: Any) -> dict[str, Any]:
    ensure_runtime_tables(conn)
    session_id = active_paper_session_id(conn)
    session = None
    if session_id:
        session = conn.execute("SELECT * FROM paper_sessions WHERE paper_session_id=%s", (session_id,)).fetchone()
    level = int((session or {}).get("defense_level") or DEFAULT_DEFENSE_LEVEL)
    profile = defense_profile(level)
    counts = learning_counts(conn, session_id)
    latest = conn.execute(
        "SELECT * FROM paper_defense_events WHERE (%s::text IS NULL OR paper_session_id=%s::text) ORDER BY created_at DESC LIMIT 1",
        (session_id, session_id),
    ).fetchone()
    return json_safe(
        {
            "status": "OK",
            "paper_only": True,
            "active_session_id": session_id,
            "defense_level": level,
            "defense_profile": profile.to_dict(),
            "threshold_scaling": {"base_paper_threshold": profile.base_threshold, "adjusted_paper_threshold": profile.adjusted_threshold},
            "capital_scaling": {
                "max_deployed_pct": profile.max_deployed_pct,
                "max_single_trade_pct": profile.max_single_trade_pct,
                "max_open_positions": profile.max_open_positions,
                "min_cash_reserve_pct": profile.min_cash_reserve_pct,
            },
            "blocker_policy_summary": blocker_policy_summary(),
            "learning_counts": counts,
            "last_changed_at": latest["created_at"] if latest else None,
            "latest_event": dict(latest) if latest else None,
        }
    )


def get_active_profile(conn: Any) -> PaperDefenseProfile:
    try:
        ensure_runtime_tables(conn)
        session_id = active_paper_session_id(conn)
        if not session_id:
            return defense_profile(DEFAULT_DEFENSE_LEVEL)
        row = conn.execute("SELECT defense_level FROM paper_sessions WHERE paper_session_id=%s", (session_id,)).fetchone()
        return defense_profile((row or {}).get("defense_level") if row else DEFAULT_DEFENSE_LEVEL)
    except Exception:
        return defense_profile(DEFAULT_DEFENSE_LEVEL)


def apply_defense_to_blockers(*, blockers: list[str], warnings: list[str], score: Decimal, profile: PaperDefenseProfile) -> dict[str, Any]:
    strict_blockers = unique_upper(blockers)
    effective_blockers: list[str] = []
    softened: list[str] = []
    ignored: list[str] = []
    fallback_required: list[str] = []
    effective_warnings = unique_upper(warnings)
    for blocker in strict_blockers:
        policy = policy_for(blocker)
        if policy.never_ignore:
            effective_blockers.append(blocker)
            continue
        if policy.category == "EXIT_REQUIREMENT" and profile.exit_fallback_enabled:
            fallback_required.append(blocker)
            softened.append(blocker)
            effective_warnings.append(f"DEFENSE_FALLBACK_EXIT_FOR_{blocker}")
            continue
        if policy.can_ignore_in_paper and profile.defense_level <= 20:
            ignored.append(blocker)
            effective_warnings.append(f"DEFENSE_IGNORED_{blocker}")
            continue
        if policy.can_soften and profile.defense_level < policy.required_defense_to_block:
            softened.append(blocker)
            effective_warnings.append(f"DEFENSE_SOFTENED_{blocker}")
            continue
        effective_blockers.append(blocker)

    if score < profile.adjusted_threshold and "OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD" not in effective_blockers and profile.defense_level >= 40:
        effective_blockers.append("OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD")

    return {
        "strict_blockers": strict_blockers,
        "effective_blockers": unique_upper(effective_blockers),
        "warnings": unique_upper(effective_warnings),
        "softened_blockers": unique_upper(softened),
        "ignored_blockers": unique_upper(ignored),
        "fallback_requirements": unique_upper(fallback_required),
        "strict_verdict": "BLOCKED" if strict_blockers else "ALLOWED",
        "effective_verdict": "BLOCKED" if effective_blockers else "ALLOWED_FOR_LEARNING" if (softened or ignored or fallback_required) else "ALLOWED",
        "exit_plan_type": "FALLBACK_LEARNING" if fallback_required else "FULL",
        "fallback_exit": fallback_exit_plan(profile, fallback_required) if fallback_required else None,
    }


def policy_for(blocker: str) -> BlockerPolicy:
    code = str(blocker or "UNKNOWN").upper()
    if code in BLOCKER_POLICY_MAP:
        return BLOCKER_POLICY_MAP[code]
    return BlockerPolicy(
        blocker_code=code,
        owner_gate="UNMAPPED",
        category="STRATEGIC_PROTECTION",
        base_type="HARD",
        can_soften=True,
        can_ignore_in_paper=True,
        never_ignore=False,
        required_defense_to_block=40,
        learning_report_label="unmapped_visible",
        explanation="Unmapped blocker is visible and defaults to strategic PAPER protection, not integrity.",
    )


def blocker_policy_summary() -> dict[str, Any]:
    policies = [policy.to_dict() for policy in BLOCKER_POLICY_MAP.values()]
    return {
        "total_mapped": len(policies),
        "integrity_never_ignore": sorted(INTEGRITY_BLOCKERS | EXECUTION_VALIDITY_BLOCKERS),
        "exit_fallback_candidates": sorted(EXIT_BLOCKERS),
        "strategic_soften_candidates": sorted(STRATEGIC_BLOCKERS),
        "policies": policies,
    }


def fallback_exit_plan(profile: PaperDefenseProfile, blockers: list[str]) -> dict[str, Any]:
    hold_minutes = 30 if profile.defense_level <= 20 else 60
    return {
        "exit_plan_type": "FALLBACK_LEARNING",
        "fallback_reason": "PAPER defense level allows learning fallback exit for incomplete strategic exit evidence.",
        "original_missing_exit_fields": blockers,
        "max_hold_minutes": hold_minutes,
        "emergency_stop_loss_pct": 35 if profile.defense_level <= 20 else 25,
        "take_profit_target_pct": 20 if profile.defense_level <= 20 else 12,
        "score_decay_exit": True,
        "liquidity_exit": True,
        "stale_data_exit": True,
        "paper_only": True,
    }


def apply_profile_to_paper_account(conn: Any, *, session_id: str, profile: PaperDefenseProfile) -> None:
    if not _table_exists(conn, "paper_accounts"):
        return
    conn.execute(
        """
        UPDATE paper_accounts
        SET risk_per_trade_pct=%s,
            max_position_size=GREATEST(current_balance * %s / 100.0, 1),
            max_open_positions=%s,
            max_total_open_exposure_pct=%s,
            metadata_json=COALESCE(metadata_json,'{}'::jsonb) || %s,
            updated_at=now()
        WHERE account_id='paper_default'
        """,
        (
            profile.max_single_trade_pct,
            profile.max_single_trade_pct,
            profile.max_open_positions,
            profile.max_deployed_pct,
            Jsonb({"paper_defense": profile.to_dict(), "paper_session_id": session_id}),
        ),
    )


def record_learning_decision(conn: Any, decision: dict[str, Any]) -> None:
    ensure_runtime_tables(conn)
    evidence = decision.get("evidence") if isinstance(decision.get("evidence"), dict) else {}
    defense = evidence.get("paper_defense") if isinstance(evidence.get("paper_defense"), dict) else {}
    session_id = active_paper_session_id(conn)
    decision_id = str(decision.get("decision_id") or "")
    if not decision_id:
        return
    ledger_id = f"paper_learning_{decision_id}_{session_id or 'no_session'}"
    conn.execute(
        """
        INSERT INTO paper_learning_ledger (
            learning_ledger_id, paper_session_id, runtime_decision_id,
            market_id, side, defense_level, strict_verdict, effective_verdict,
            strict_blockers_json, effective_blockers_json, ignored_blockers_json,
            softened_blockers_json, fallback_requirements_json, base_threshold,
            adjusted_threshold, opportunity_score, exit_plan_type, entry_metadata_json
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (learning_ledger_id) DO UPDATE SET
            defense_level=EXCLUDED.defense_level,
            strict_verdict=EXCLUDED.strict_verdict,
            effective_verdict=EXCLUDED.effective_verdict,
            strict_blockers_json=EXCLUDED.strict_blockers_json,
            effective_blockers_json=EXCLUDED.effective_blockers_json,
            ignored_blockers_json=EXCLUDED.ignored_blockers_json,
            softened_blockers_json=EXCLUDED.softened_blockers_json,
            fallback_requirements_json=EXCLUDED.fallback_requirements_json,
            base_threshold=EXCLUDED.base_threshold,
            adjusted_threshold=EXCLUDED.adjusted_threshold,
            opportunity_score=EXCLUDED.opportunity_score,
            exit_plan_type=EXCLUDED.exit_plan_type,
            entry_metadata_json=EXCLUDED.entry_metadata_json,
            updated_at=now()
        """,
        (
            ledger_id,
            session_id,
            decision_id,
            decision.get("market_id"),
            decision.get("side"),
            int(defense.get("defense_level") or DEFAULT_DEFENSE_LEVEL),
            str(defense.get("strict_verdict") or "UNKNOWN"),
            str(defense.get("effective_verdict") or "UNKNOWN"),
            Jsonb(defense.get("strict_blockers") or []),
            Jsonb(defense.get("effective_blockers") or decision.get("blockers_json") or []),
            Jsonb(defense.get("ignored_blockers") or []),
            Jsonb(defense.get("softened_blockers") or []),
            Jsonb(defense.get("fallback_requirements") or []),
            _decimal_or_none(defense.get("base_threshold")),
            _decimal_or_none(defense.get("adjusted_threshold")),
            _decimal_or_none(decision.get("opportunity_score")),
            str(defense.get("exit_plan_type") or "FULL"),
            Jsonb(json_safe({"decision": decision, "paper_defense": defense})),
        ),
    )


def learning_counts(conn: Any, session_id: str | None) -> dict[str, int]:
    if not _table_exists(conn, "paper_learning_ledger"):
        return {"learning_entries": 0, "ignored_blockers": 0, "softened_blockers": 0, "fallback_exits": 0}
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS learning_entries,
            COALESCE(SUM(jsonb_array_length(ignored_blockers_json)),0) AS ignored_blockers,
            COALESCE(SUM(jsonb_array_length(softened_blockers_json)),0) AS softened_blockers,
            COUNT(*) FILTER (WHERE exit_plan_type='FALLBACK_LEARNING') AS fallback_exits
        FROM paper_learning_ledger
        WHERE (%s::text IS NULL OR paper_session_id=%s::text)
        """,
        (session_id, session_id),
    ).fetchone()
    return {key: int(row[key] or 0) for key in ("learning_entries", "ignored_blockers", "softened_blockers", "fallback_exits")} if row else {}


def build_learning_report(conn: Any, session_id: str) -> dict[str, Any]:
    session = conn.execute("SELECT * FROM paper_sessions WHERE paper_session_id=%s", (session_id,)).fetchone()
    counts = learning_counts(conn, session_id)
    trades = _fetchall(
        conn,
        """
        SELECT
            pi.paper_intent_id AS trade_id,
            pi.market_id,
            pi.side,
            pi.created_at AS entry_time,
            pf.fill_price AS entry_price,
            pf.quantity AS size,
            pc.created_at AS exit_time,
            pc.exit_price,
            pc.realized_pnl AS pnl,
            pc.exit_reason,
            pf.metadata_json->>'execution_price_source' AS execution_price_source,
            COALESCE((pf.metadata_json->>'trusted_orderbook_used')::boolean, false) AS trusted_orderbook_used,
            pf.metadata_json->>'fallback_source' AS fallback_source,
            pf.metadata_json->>'fallback_reason' AS fallback_reason,
            pf.metadata_json->>'price_confidence' AS price_confidence,
            COALESCE((pf.metadata_json->>'fallback_learning_only')::boolean, false) AS fallback_learning_only,
            pf.metadata_json->>'orderbook_snapshot_id' AS execution_orderbook_snapshot_id,
            pf.metadata_json->>'price_age_seconds' AS price_age_seconds,
            pf.metadata_json->>'spread' AS spread,
            pf.metadata_json->>'slippage_model' AS slippage_model,
            pi.evidence->'paper_defense' AS paper_defense
        FROM paper_intents pi
        LEFT JOIN paper_fills pf ON pf.source_intent_id=pi.paper_intent_id
        LEFT JOIN paper_position_closes pc ON pc.paper_session_id=pi.paper_session_id AND pc.market_id=pi.market_id AND pc.side=pi.side
        WHERE pi.paper_session_id=%s
        ORDER BY pi.created_at ASC
        """,
        (session_id,),
    ) if _table_exists(conn, "paper_intents") else []
    blockers = _fetchall(
        conn,
        """
        SELECT item AS blocker, COUNT(*) AS count
        FROM paper_learning_ledger, jsonb_array_elements_text(strict_blockers_json) AS item
        WHERE paper_session_id=%s
        GROUP BY item
        ORDER BY count DESC, blocker ASC
        LIMIT 20
        """,
        (session_id,),
    ) if _table_exists(conn, "paper_learning_ledger") else []
    ignored = _fetchall(
        conn,
        """
        SELECT item AS blocker, COUNT(*) AS count
        FROM paper_learning_ledger, jsonb_array_elements_text(ignored_blockers_json) AS item
        WHERE paper_session_id=%s
        GROUP BY item
        ORDER BY count DESC, blocker ASC
        LIMIT 20
        """,
        (session_id,),
    ) if _table_exists(conn, "paper_learning_ledger") else []
    softened = _fetchall(
        conn,
        """
        SELECT item AS blocker, COUNT(*) AS count
        FROM paper_learning_ledger, jsonb_array_elements_text(softened_blockers_json) AS item
        WHERE paper_session_id=%s
        GROUP BY item
        ORDER BY count DESC, blocker ASC
        LIMIT 20
        """,
        (session_id,),
    ) if _table_exists(conn, "paper_learning_ledger") else []
    opportunity_mesh_summary: dict[str, Any] = {"status": "UNAVAILABLE"}
    candidate_consumption_summary: dict[str, Any] = {}
    intent_queue_summary: dict[str, Any] = {}
    opportunity_memory_summary: dict[str, Any] = {}
    expired_intents_summary: dict[str, Any] = {}
    try:
        from app.services.opportunity_mesh_coordinator import OpportunityMeshCoordinator
        from app.services.opportunity_memory import OpportunityMemoryService

        mesh_payload = OpportunityMeshCoordinator().opportunity_mesh_for_connection(conn, limit=50, session_id=session_id)
        opportunity_mesh_summary = mesh_payload.get("summary") or {"status": mesh_payload.get("status")}
        candidate_consumption_summary = mesh_payload.get("candidate_consumption") or {}
        queue_items = mesh_payload.get("intent_queue") or []
        intent_queue_summary = {
            "active_intents": len(queue_items),
            "intent_stuck": sum(1 for item in queue_items if item.get("stuck")),
            "intent_expired": sum(1 for item in queue_items if item.get("expired")),
            "intent_cancelled": sum(1 for item in queue_items if item.get("cancelled")),
            "pending_execution": sum(1 for item in queue_items if item.get("execution_status") == "INTENT_PENDING_EXECUTION"),
        }
        memory_service = OpportunityMemoryService()
        opportunity_memory_summary = memory_service.opportunity_memory_for_connection(conn, limit=50, session_id=session_id).get("counts") or {}
        expired_intents_summary = memory_service.expired_intents_for_connection(conn, limit=50, session_id=session_id).get("counts") or {}
    except Exception as exc:
        opportunity_mesh_summary = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
    realized = sum(_decimal_or_zero(row.get("pnl")) for row in trades)
    wins = [row for row in trades if _decimal_or_zero(row.get("pnl")) > 0]
    losses = [row for row in trades if _decimal_or_zero(row.get("pnl")) < 0]
    return json_safe(
        {
            "status": "OK",
            "schema_version": "paper_session_learning_report_v1",
            "session_metadata": {
                "session_id": session_id,
                "started_at": session["started_at"] if session else None,
                "ended_at": session["closed_at"] if session else None,
                "defense_level": (session or {}).get("defense_level") or DEFAULT_DEFENSE_LEVEL,
                "starting_balance": (session or {}).get("starting_balance"),
                "max_deployed_pct": (session or {}).get("max_deployed_pct"),
                "max_single_trade_pct": (session or {}).get("max_single_trade_pct"),
            },
            "result_summary": {
                "realized_pnl": realized,
                "unrealized_pnl": Decimal("0"),
                "net_pnl": realized,
                "number_of_entries": len(trades),
                "number_of_exits": len([row for row in trades if row.get("exit_time")]),
                "open_positions_end": _count_session(conn, "paper_positions", session_id, "closed_at IS NULL") if _table_exists(conn, "paper_positions") else 0,
                "win_rate": (len(wins) / len(trades)) if trades else 0,
                "avg_win": (sum(_decimal_or_zero(row.get("pnl")) for row in wins) / len(wins)) if wins else 0,
                "avg_loss": (sum(_decimal_or_zero(row.get("pnl")) for row in losses) / len(losses)) if losses else 0,
            },
            "hunting_summary": {
                "runtime_decisions": _count_session(conn, "paper_learning_ledger", session_id) if _table_exists(conn, "paper_learning_ledger") else 0,
                "top_blockers": blockers,
                "top_ignored_blockers": ignored,
                "top_softened_blockers": softened,
                "opportunity_mesh_summary": opportunity_mesh_summary,
                "candidate_consumption_summary": candidate_consumption_summary,
                "intent_queue_summary": intent_queue_summary,
                "opportunity_memory_summary": opportunity_memory_summary,
                "expired_intents_summary": expired_intents_summary,
                **counts,
            },
            "trade_table": trades,
            "learning_analysis": {
                "ignored_blockers_that_led_to_winning_trades": [],
                "ignored_blockers_that_led_to_losing_trades": [],
                "blockers_that_may_be_too_strict": ignored[:10],
                "score_bands_performance": [],
                "exit_type_performance": [],
                "opportunity_memory": opportunity_memory_summary,
                "expired_intents": expired_intents_summary,
                "suggested_defense_adjustments": "Review ignored/softened blocker outcomes after more closed trades.",
            },
            "machine_learning_export": {"schema_version": 1, "rows": trades},
        }
    )


def write_learning_report_files(report: dict[str, Any], root: Path) -> dict[str, str]:
    session_id = str(report.get("session_metadata", {}).get("session_id") or "unknown_session")
    report_dir = root / f"paper_session_learning_{session_id}"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"paper_session_learning_report_{session_id}.json"
    md_path = report_dir / f"paper_session_learning_report_{session_id}.md"
    csv_path = report_dir / f"paper_session_trades_{session_id}.csv"
    json_path.write_text(json.dumps(json_safe(report), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_markdown_report(report), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "trade_id",
                "market_id",
                "side",
                "entry_time",
                "exit_time",
                "entry_price",
                "exit_price",
                "size",
                "pnl",
                "exit_reason",
                "execution_price_source",
                "trusted_orderbook_used",
                "fallback_source",
                "fallback_reason",
                "price_confidence",
                "price_age_seconds",
                "spread",
            ],
        )
        writer.writeheader()
        for row in report.get("trade_table") or []:
            writer.writerow({key: row.get(key) for key in writer.fieldnames})
    return {"json": str(json_path), "md": str(md_path), "csv": str(csv_path)}


def ensure_runtime_tables(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_defense_events (
            id BIGSERIAL PRIMARY KEY,
            event_id TEXT NOT NULL UNIQUE,
            paper_session_id TEXT,
            old_defense_level INTEGER,
            new_defense_level INTEGER NOT NULL,
            reason TEXT,
            actor TEXT,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_learning_ledger (
            id BIGSERIAL PRIMARY KEY,
            learning_ledger_id TEXT NOT NULL UNIQUE,
            paper_session_id TEXT,
            runtime_decision_id TEXT,
            paper_intent_id TEXT,
            market_id TEXT,
            side TEXT,
            defense_level INTEGER NOT NULL DEFAULT 100,
            strict_verdict TEXT NOT NULL DEFAULT 'UNKNOWN',
            effective_verdict TEXT NOT NULL DEFAULT 'UNKNOWN',
            strict_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            effective_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            ignored_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            softened_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            fallback_requirements_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            base_threshold NUMERIC(12,4),
            adjusted_threshold NUMERIC(12,4),
            opportunity_score NUMERIC(12,4),
            exit_plan_type TEXT,
            entry_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            exit_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    if _table_exists(conn, "paper_sessions"):
        for ddl in (
            "ALTER TABLE paper_sessions ADD COLUMN IF NOT EXISTS defense_level INTEGER NOT NULL DEFAULT 100",
            "ALTER TABLE paper_sessions ADD COLUMN IF NOT EXISTS defense_profile_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE paper_sessions ADD COLUMN IF NOT EXISTS max_deployed_pct NUMERIC(8,4)",
            "ALTER TABLE paper_sessions ADD COLUMN IF NOT EXISTS max_single_trade_pct NUMERIC(8,4)",
            "ALTER TABLE paper_sessions ADD COLUMN IF NOT EXISTS session_learning_report_path TEXT",
        ):
            conn.execute(ddl)


def unique_upper(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        code = str(value or "").upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _render_markdown_report(report: dict[str, Any]) -> str:
    meta = report.get("session_metadata") or {}
    result = report.get("result_summary") or {}
    hunting = report.get("hunting_summary") or {}
    trades = report.get("trade_table") or []
    fallback_trades = sum(1 for row in trades if str(row.get("execution_price_source") or "").upper() == "PAPER_LEARNING_PRICE_FALLBACK")
    trusted_trades = sum(1 for row in trades if row.get("trusted_orderbook_used"))
    return "\n".join(
        [
            "# Paper Session Learning Report",
            "",
            f"Session: {meta.get('session_id')}",
            f"Defense level: {meta.get('defense_level')}",
            f"Starting balance: {meta.get('starting_balance')}",
            "",
            "## Result Summary",
            f"Realized PnL: {result.get('realized_pnl')}",
            f"Net PnL: {result.get('net_pnl')}",
            f"Entries: {result.get('number_of_entries')}",
            f"Exits: {result.get('number_of_exits')}",
            "",
            "## Hunting Summary",
            f"Runtime decisions: {hunting.get('runtime_decisions')}",
            f"Ignored blockers: {hunting.get('ignored_blockers')}",
            f"Softened blockers: {hunting.get('softened_blockers')}",
            f"Fallback exits: {hunting.get('fallback_exits')}",
            f"Expired intents: {hunting.get('expired_intents_summary')}",
            f"Opportunity memory: {hunting.get('opportunity_memory_summary')}",
            "",
            "## Execution Pricing",
            f"Trusted orderbook executions: {trusted_trades}",
            f"Paper learning fallback executions: {fallback_trades}",
        ]
    )


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _count_session(conn: Any, table: str, session_id: str, extra_where: str | None = None) -> int:
    where = "paper_session_id=%s"
    if extra_where:
        where = f"{where} AND {extra_where}"
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}", (session_id,)).fetchone()
    return int((row or {}).get("count") or 0)


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _decimal_or_zero(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")
