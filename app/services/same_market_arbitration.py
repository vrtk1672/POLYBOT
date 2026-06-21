from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_defense import DEFAULT_DEFENSE_LEVEL, INTEGRITY_BLOCKERS, defense_profile, get_active_profile
from app.services.paper_session import active_paper_session_id
from app.services.side_evidence import SideEvidenceScorer
from app.utils.json_safety import json_safe


CONFLICT_BLOCKERS = {
    "SAME_MARKET_OPPOSING_ENTER_CONFLICT",
    "SAME_MARKET_OPPOSING_SIDE_BLOCK",
    "SAME_MARKET_OPPOSING_SIDE_LOST_ARBITRATION",
    "SAME_MARKET_BATCH_CONFLICT_BLOCK",
    "SAME_MARKET_OPPOSING_SIDE_UNRESOLVED",
    "OPPOSING_SIDE_DEMOTED_BY_ARBITRATION",
}


@dataclass(frozen=True)
class SideScore:
    decision: dict[str, Any]
    side: str
    score: Decimal
    impossible: bool
    evidence: dict[str, Any]


class SameMarketSideArbitrator:
    """Defense-aware same-market YES/NO arbitration before PaperIntentGate."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        defense_level: int | None = None,
        side_evidence_scorer: SideEvidenceScorer | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._defense_level = defense_level
        self._side_evidence = side_evidence_scorer or SideEvidenceScorer()

    def arbitrate(self, decisions: list[dict[str, Any]], *, conn: Any | None = None) -> list[dict[str, Any]]:
        profile = get_active_profile(conn) if conn is not None else defense_profile(self._defense_level if self._defense_level is not None else DEFAULT_DEFENSE_LEVEL)
        session_id = active_paper_session_id(conn) if conn is not None else None
        by_market: dict[str, list[dict[str, Any]]] = {}
        for decision in decisions:
            if str(decision.get("decision") or "").upper() == "ENTER" and decision.get("market_id"):
                by_market.setdefault(str(decision["market_id"]), []).append(decision)

        for market_id, market_decisions in by_market.items():
            sides = {str(item.get("side") or "").upper() for item in market_decisions}
            if not {"YES", "NO"}.issubset(sides):
                continue
            side_scores = self._best_side_scores(market_decisions, conn=conn)
            result = self._resolve(market_id=market_id, session_id=session_id, side_scores=side_scores, defense_level=profile.defense_level)
            self._apply_result(market_id=market_id, market_decisions=market_decisions, side_scores=side_scores, result=result)
            if conn is not None:
                ensure_arbitration_tables(conn)
                _record_arbitration(conn, result)
        return decisions

    def dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "items": []}
        with self._factory.connect() as conn:
            ensure_arbitration_tables(conn)
            session_id = active_paper_session_id(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM same_market_side_arbitrations
                WHERE (%s::text IS NULL OR paper_session_id=%s::text)
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (session_id, session_id, max(1, min(int(limit or 20), 100))),
            ).fetchall()
            counts = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_conflicts,
                    COUNT(*) FILTER (WHERE selected_side IS NOT NULL) AS resolved_conflicts,
                    COUNT(*) FILTER (WHERE selected_side IS NULL) AS unresolved_conflicts,
                    COUNT(*) FILTER (WHERE outcome='ARBITRATION_SELECTED_BY_SIDE_EVIDENCE') AS resolved_by_side_evidence,
                    COUNT(*) FILTER (WHERE outcome='ARBITRATION_SELECTED_BY_ORDERBOOK') AS resolved_by_orderbook,
                    COUNT(*) FILTER (WHERE outcome IN ('TIE_BROKEN_BY_DEFENSE_ZERO','TIE_BROKEN_BY_DETERMINISTIC_RULE','TIE_BROKEN_FOR_LEARNING','ARBITRATION_SELECTED_BY_ORDERBOOK','ARBITRATION_SELECTED_BY_LIQUIDITY','ARBITRATION_SELECTED_BY_EXIT_READINESS')) AS tie_broken_count
                FROM same_market_side_arbitrations
                WHERE (%s::text IS NULL OR paper_session_id=%s::text)
                """,
                (session_id, session_id),
            ).fetchone() or {}
            return json_safe(
                {
                    "status": "OK",
                    "active_paper_session_id": session_id,
                    "counts": dict(counts),
                    "items": [dict(row) for row in rows],
                    "latest": dict(rows[0]) if rows else None,
                }
            )

    def _best_side_scores(self, decisions: list[dict[str, Any]], *, conn: Any | None = None) -> dict[str, SideScore]:
        best: dict[str, SideScore] = {}
        for decision in decisions:
            side = str(decision.get("side") or "").upper()
            if side not in {"YES", "NO"}:
                continue
            scored = _score_side(decision, side_evidence_scorer=self._side_evidence, conn=conn)
            current = best.get(side)
            if current is None or scored.score > current.score:
                best[side] = scored
        return best

    def _resolve(
        self,
        *,
        market_id: str,
        session_id: str | None,
        side_scores: dict[str, SideScore],
        defense_level: int,
    ) -> dict[str, Any]:
        yes = side_scores.get("YES")
        no = side_scores.get("NO")
        required_margin = _required_margin(defense_level)
        now = datetime.now(UTC)
        result: dict[str, Any] = {
            "arbitration_id": f"same_market_arbitration_{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
            "paper_session_id": session_id,
            "market_id": market_id,
            "defense_level": defense_level,
            "yes_decision_id": (yes.decision.get("decision_id") if yes else None),
            "no_decision_id": (no.decision.get("decision_id") if no else None),
            "yes_score": yes.decision.get("opportunity_score") if yes else None,
            "no_score": no.decision.get("opportunity_score") if no else None,
            "yes_arbitration_score": yes.score if yes else None,
            "no_arbitration_score": no.score if no else None,
            "selected_side": None,
            "rejected_side": None,
            "margin": None,
            "required_margin": required_margin,
            "tie_breaker_used": None,
            "outcome": "SAME_MARKET_OPPOSING_SIDE_UNRESOLVED",
            "conflict_type": "OPPOSING_ENTER",
            "ignored_or_softened_conflict": defense_level <= 20,
            "strict_verdict": "BLOCKED",
            "effective_verdict": "BLOCKED",
            "reason": "YES/NO evidence is unresolved.",
            "yes_evidence_json": yes.evidence if yes else {},
            "no_evidence_json": no.evidence if no else {},
            "yes_side_evidence_score": (yes.evidence.get("side_evidence", {}) or {}).get("side_evidence_score") if yes else None,
            "no_side_evidence_score": (no.evidence.get("side_evidence", {}) or {}).get("side_evidence_score") if no else None,
            "yes_evidence_quality": (yes.evidence.get("side_evidence", {}) or {}).get("evidence_quality") if yes else None,
            "no_evidence_quality": (no.evidence.get("side_evidence", {}) or {}).get("evidence_quality") if no else None,
            "side_unknown_count": _side_unknown_count(yes.evidence if yes else {}, no.evidence if no else {}),
            "missing_side_evidence_json": _missing_side_evidence(yes.evidence if yes else {}, no.evidence if no else {}),
            "metadata_json": {"paper_only": True, "source": "same_market_side_arbitrator", "side_evidence_model": "v1"},
        }
        if not yes or not no:
            return result
        if yes.impossible and no.impossible:
            result.update(
                {
                    "outcome": "INTEGRITY_BLOCKER_PREVENTED_ARBITRATION",
                    "reason": "Both sides have integrity blockers and cannot be selected.",
                    "effective_verdict": "INTEGRITY_BLOCK",
                }
            )
            return result
        if yes.impossible or no.impossible:
            winner = no if yes.impossible else yes
            loser = yes if yes.impossible else no
            return _selected_result(result, winner=winner, loser=loser, outcome=f"ARBITRATION_SELECTED_{winner.side}", reason=f"{loser.side} had integrity blockers; {winner.side} remains technically executable.")

        margin = abs(yes.score - no.score)
        result["margin"] = margin
        if margin >= required_margin and yes.score != no.score:
            winner, loser = (yes, no) if yes.score > no.score else (no, yes)
            outcome = _selection_outcome(winner, loser)
            return _selected_result(
                result,
                winner=winner,
                loser=loser,
                outcome=outcome,
                reason=f"{winner.side} arbitration score exceeded {loser.side} by {margin}.",
            )

        tie = _tie_breaker(yes, no, market_id=market_id, session_id=session_id)
        if defense_level <= 20 and tie.get("selected_side"):
            winner = yes if tie["selected_side"] == "YES" else no
            loser = no if winner is yes else yes
            outcome = "TIE_BROKEN_FOR_LEARNING" if yes.score == no.score else _tie_break_outcome(str(tie.get("tie_breaker_used") or ""))
            selected = _selected_result(
                result,
                winner=winner,
                loser=loser,
                outcome=outcome,
                reason=f"{winner.side} selected by {tie['tie_breaker_used']} under Defense {defense_level}.",
            )
            selected["tie_breaker_used"] = tie["tie_breaker_used"]
            selected["metadata_json"]["low_confidence_selection"] = margin < required_margin
            return selected

        result.update(
            {
                "outcome": "SAME_MARKET_OPPOSING_SIDE_UNRESOLVED",
                "reason": f"Observed margin {margin} is below required margin {required_margin} for Defense {defense_level}.",
                "tie_breaker_used": tie.get("tie_breaker_used"),
            }
        )
        return result

    def _apply_result(
        self,
        *,
        market_id: str,
        market_decisions: list[dict[str, Any]],
        side_scores: dict[str, SideScore],
        result: dict[str, Any],
    ) -> None:
        selected_side = result.get("selected_side")
        selected_decision = side_scores.get(str(selected_side)) .decision if selected_side and side_scores.get(str(selected_side)) else None
        for item in market_decisions:
            side = str(item.get("side") or "").upper()
            if selected_decision is not None and item is selected_decision:
                item["warnings_json"] = _unique([*_list(item.get("warnings_json")), "SAME_MARKET_OPPOSING_SIDE_ARBITRATION_WINNER"])
                _append_arbitration_evidence(item, market_id=market_id, state="WINNER", result=result)
                policy = _dict(item.get("policy_json"))
                policy["opposing_side_arbitration"] = "WINNER"
                policy["same_market_side_arbitration"] = json_safe(result)
                item["policy_json"] = policy
                continue
            if selected_side:
                _demote(
                    item,
                    blocker="OPPOSING_SIDE_DEMOTED_BY_ARBITRATION",
                    required="The opposite side won same-market side arbitration for this PAPER batch.",
                    state="DEMOTED",
                    result=result,
                )
            else:
                blocker = "INTEGRITY_BLOCKER_PREVENTED_ARBITRATION" if result.get("outcome") == "INTEGRITY_BLOCKER_PREVENTED_ARBITRATION" else "SAME_MARKET_OPPOSING_SIDE_UNRESOLVED"
                _demote(
                    item,
                    blocker=blocker,
                    required="Resolve same-market YES/NO evidence before paper intent creation.",
                    state="UNRESOLVED",
                    result=result,
                    include_legacy_conflict=True,
                )


def ensure_arbitration_tables(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS same_market_side_arbitrations (
            id BIGSERIAL PRIMARY KEY,
            arbitration_id TEXT NOT NULL UNIQUE,
            paper_session_id TEXT,
            market_id TEXT NOT NULL,
            defense_level INTEGER NOT NULL DEFAULT 100,
            yes_decision_id TEXT,
            no_decision_id TEXT,
            yes_score NUMERIC(18,8),
            no_score NUMERIC(18,8),
            yes_arbitration_score NUMERIC(18,8),
            no_arbitration_score NUMERIC(18,8),
            selected_side TEXT,
            rejected_side TEXT,
            margin NUMERIC(18,8),
            required_margin NUMERIC(18,8) NOT NULL DEFAULT 0,
            tie_breaker_used TEXT,
            outcome TEXT NOT NULL,
            conflict_type TEXT NOT NULL DEFAULT 'OPPOSING_ENTER',
            ignored_or_softened_conflict BOOLEAN NOT NULL DEFAULT false,
            strict_verdict TEXT NOT NULL DEFAULT 'BLOCKED',
            effective_verdict TEXT NOT NULL DEFAULT 'UNKNOWN',
            reason TEXT NOT NULL DEFAULT '',
            yes_evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            no_evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            yes_side_evidence_score NUMERIC(18,8),
            no_side_evidence_score NUMERIC(18,8),
            yes_evidence_quality TEXT,
            no_evidence_quality TEXT,
            side_unknown_count INTEGER NOT NULL DEFAULT 0,
            missing_side_evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute("ALTER TABLE same_market_side_arbitrations ADD COLUMN IF NOT EXISTS yes_side_evidence_score NUMERIC(18,8)")
    conn.execute("ALTER TABLE same_market_side_arbitrations ADD COLUMN IF NOT EXISTS no_side_evidence_score NUMERIC(18,8)")
    conn.execute("ALTER TABLE same_market_side_arbitrations ADD COLUMN IF NOT EXISTS yes_evidence_quality TEXT")
    conn.execute("ALTER TABLE same_market_side_arbitrations ADD COLUMN IF NOT EXISTS no_evidence_quality TEXT")
    conn.execute("ALTER TABLE same_market_side_arbitrations ADD COLUMN IF NOT EXISTS side_unknown_count INTEGER NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE same_market_side_arbitrations ADD COLUMN IF NOT EXISTS missing_side_evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_same_market_side_arbitrations_session ON same_market_side_arbitrations(paper_session_id, created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_same_market_side_arbitrations_market ON same_market_side_arbitrations(market_id, created_at DESC)")


def _score_side(decision: dict[str, Any], *, side_evidence_scorer: SideEvidenceScorer | None = None, conn: Any | None = None) -> SideScore:
    blockers = [str(item).upper() for item in _list(decision.get("blockers_json"))]
    warnings = [str(item).upper() for item in _list(decision.get("warnings_json"))]
    evidence = _dict(decision.get("evidence"))
    source = _dict(evidence.get("source_evidence"))
    defense = _dict(evidence.get("paper_defense"))
    score = _decimal(decision.get("opportunity_score"))
    details: dict[str, Any] = {"base_opportunity_score": score, "bonuses": {}, "penalties": {}, "blockers": blockers, "warnings": warnings}
    side_model = (side_evidence_scorer or SideEvidenceScorer()).score_decision(decision, conn=conn)
    side_payload = side_model.to_dict()
    side_score = _decimal(side_payload.get("side_evidence_score"))
    details["side_evidence"] = side_payload
    details["side_evidence_score"] = side_score
    details["direction_confidence"] = side_payload.get("direction_confidence")
    score += side_score
    if side_score > 0:
        details["bonuses"]["side_evidence_score"] = side_score
    elif side_score < 0:
        details["penalties"]["side_evidence_score"] = abs(side_score)

    impossible = bool((set(blockers) - CONFLICT_BLOCKERS) & INTEGRITY_BLOCKERS)
    if impossible:
        details["penalties"]["integrity_blocker"] = Decimal("-999")
        score += Decimal("-999")

    thesis_state = str(decision.get("thesis_state") or source.get("thesis_state") or "").upper()
    edge_state = str(decision.get("edge_state") or source.get("edge_state") or "").upper()
    exit_state = str(decision.get("exit_state") or source.get("exit_state") or "").upper()
    token_state = str(decision.get("token_verification_state") or "").upper()
    orderbook_state = str(decision.get("orderbook_state") or "").upper()
    if thesis_state in {"THESIS_SUPPORTED", "VALID", "COMPLETE"}:
        score += _bonus(details, "thesis_supported", 6)
    elif thesis_state in {"THESIS_WATCH", "WATCH"}:
        score += _bonus(details, "thesis_watch", 3)
    elif "THESIS_NOT_SUPPORTED" in blockers or "THESIS_MISSING" in blockers:
        score += _penalty(details, "thesis_missing", 5)

    if edge_state == "EDGE_SUPPORTED":
        score += _bonus(details, "edge_supported", 6)
    elif "EDGE_NOT_SUPPORTED" in blockers:
        score += _penalty(details, "edge_missing", 4)

    fallback_exit = str(defense.get("exit_plan_type") or "").upper() == "FALLBACK_LEARNING"
    if exit_state in {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}:
        score += _bonus(details, "exit_ready", 6)
    elif fallback_exit:
        score += _bonus(details, "fallback_exit_available", 3)
    elif "EXIT_NOT_READY" in blockers:
        score += _penalty(details, "exit_missing_no_fallback", 6)

    orderbook_age = _decimal(evidence.get("orderbook_age_seconds"))
    ttl = _decimal(evidence.get("orderbook_ttl_seconds") or 60)
    if orderbook_state in {"FRESH", "ORDERBOOK_FRESH"} or (orderbook_age >= 0 and orderbook_age <= ttl):
        score += _bonus(details, "orderbook_fresh", 4)
    elif "ORDERBOOK_NOT_FRESH" in blockers or "STALE_ORDERBOOK" in blockers:
        score += _penalty(details, "stale_orderbook", 5)

    spread = _spread(evidence)
    liquidity_score = _liquidity_score(evidence, spread)
    details["orderbook_spread"] = spread
    details["liquidity_score"] = liquidity_score
    if liquidity_score is not None and liquidity_score >= Decimal("0.70"):
        score += _bonus(details, "good_liquidity", 4)
    elif liquidity_score is not None and liquidity_score < Decimal("0.35"):
        score += _penalty(details, "weak_liquidity", 3)

    side = str(decision.get("side") or "").upper()
    if side not in {"YES", "NO"}:
        score += _penalty(details, "side_unknown", 8)
    elif token_state in {"TOKENS_VERIFIED", "TOKEN_SIDE_DIRECT", f"SIDE_DIRECTIONAL_{side}"} or decision.get("token_id"):
        score += _bonus(details, "direct_side_evidence", 4)

    if orderbook_age >= 0 and orderbook_age <= ttl:
        score += _bonus(details, "recent_data", 2)

    strategic_blockers = [code for code in blockers if code not in INTEGRITY_BLOCKERS and code not in CONFLICT_BLOCKERS]
    if strategic_blockers:
        penalty = min(Decimal("12"), Decimal(len(strategic_blockers) * 2))
        details["penalties"]["blocker_severity"] = penalty
        score -= penalty
    details["final_arbitration_score"] = score
    return SideScore(decision=decision, side=side, score=score, impossible=impossible, evidence=json_safe(details))


def _selected_result(result: dict[str, Any], *, winner: SideScore, loser: SideScore, outcome: str, reason: str) -> dict[str, Any]:
    margin = abs(winner.score - loser.score)
    result.update(
        {
            "selected_side": winner.side,
            "rejected_side": loser.side,
            "margin": margin,
            "outcome": outcome,
            "strict_verdict": "BLOCKED",
            "effective_verdict": "ALLOWED_AFTER_ARBITRATION",
            "reason": reason,
        }
    )
    return result


def _selection_outcome(winner: SideScore, loser: SideScore) -> str:
    winner_side_score = _decimal((winner.evidence.get("side_evidence", {}) or {}).get("side_evidence_score"))
    loser_side_score = _decimal((loser.evidence.get("side_evidence", {}) or {}).get("side_evidence_score"))
    if winner_side_score > loser_side_score:
        return "ARBITRATION_SELECTED_BY_SIDE_EVIDENCE"
    if _decimal(winner.evidence.get("liquidity_score")) > _decimal(loser.evidence.get("liquidity_score")):
        return "ARBITRATION_SELECTED_BY_LIQUIDITY"
    if _decimal(winner.evidence.get("bonuses", {}).get("exit_ready")) > _decimal(loser.evidence.get("bonuses", {}).get("exit_ready")):
        return "ARBITRATION_SELECTED_BY_EXIT_READINESS"
    return f"ARBITRATION_SELECTED_{winner.side}"


def _tie_break_outcome(tie_breaker: str) -> str:
    if tie_breaker == "fresher_orderbook":
        return "ARBITRATION_SELECTED_BY_ORDERBOOK"
    if tie_breaker == "better_liquidity_or_spread":
        return "ARBITRATION_SELECTED_BY_LIQUIDITY"
    if tie_breaker == "better_exit_readiness":
        return "ARBITRATION_SELECTED_BY_EXIT_READINESS"
    if tie_breaker == "stronger_side_specific_evidence":
        return "ARBITRATION_SELECTED_BY_SIDE_EVIDENCE"
    return "TIE_BROKEN_BY_DETERMINISTIC_RULE"


def _side_unknown_count(yes_evidence: dict[str, Any], no_evidence: dict[str, Any]) -> int:
    count = 0
    for evidence in (yes_evidence, no_evidence):
        side_model = evidence.get("side_evidence", {}) if isinstance(evidence.get("side_evidence"), dict) else {}
        if _decimal(side_model.get("side_unknown_penalty")) > 0:
            count += 1
    return count


def _missing_side_evidence(yes_evidence: dict[str, Any], no_evidence: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for label, evidence in (("YES", yes_evidence), ("NO", no_evidence)):
        side_model = evidence.get("side_evidence", {}) if isinstance(evidence.get("side_evidence"), dict) else {}
        for item in _list(side_model.get("missing_reasons")):
            missing.append(f"{label}:{item}")
    return _unique(missing)


def _tie_breaker(yes: SideScore, no: SideScore, *, market_id: str, session_id: str | None) -> dict[str, Any]:
    comparisons = [
        ("fresher_orderbook", _compare_lower(yes.evidence.get("orderbook_age_seconds"), no.evidence.get("orderbook_age_seconds"))),
        ("better_liquidity_or_spread", _compare_higher(yes.evidence.get("liquidity_score"), no.evidence.get("liquidity_score"))),
        ("better_exit_readiness", _compare_bonus(yes, no, "exit_ready", "fallback_exit_available")),
        ("better_thesis_state", _compare_bonus(yes, no, "thesis_supported", "thesis_watch")),
        ("stronger_side_specific_evidence", _compare_higher((yes.evidence.get("side_evidence", {}) or {}).get("side_evidence_score"), (no.evidence.get("side_evidence", {}) or {}).get("side_evidence_score"))),
    ]
    for name, selected in comparisons:
        if selected:
            return {"selected_side": selected, "tie_breaker_used": name}
    digest = hashlib.sha256(f"{market_id}:{session_id or 'no-session'}".encode("utf-8")).hexdigest()
    return {"selected_side": "YES" if int(digest[:2], 16) % 2 == 0 else "NO", "tie_breaker_used": "deterministic_hash_market_session"}


def _demote(
    decision: dict[str, Any],
    *,
    blocker: str,
    required: str,
    state: str,
    result: dict[str, Any],
    include_legacy_conflict: bool = False,
) -> None:
    blockers = _unique([*_list(decision.get("blockers_json")), blocker])
    if include_legacy_conflict:
        blockers = _unique([*blockers, "SAME_MARKET_OPPOSING_ENTER_CONFLICT"])
    decision["decision"] = "BLOCK"
    decision["paper_enter_allowed"] = False
    decision["blockers_json"] = blockers
    decision["required_to_pass_json"] = _unique([*_list(decision.get("required_to_pass_json")), required])
    decision["warnings_json"] = _unique([*_list(decision.get("warnings_json")), "PAPER_BATCH_OPPOSING_SIDE_ARBITRATED"])
    policy = _dict(decision.get("policy_json"))
    policy["opposing_side_arbitration"] = state
    policy["paper_enter_allowed"] = False
    policy["same_market_side_arbitration"] = json_safe(result)
    decision["policy_json"] = policy
    _append_arbitration_evidence(decision, market_id=str(decision.get("market_id") or ""), state=state, result=result)


def _append_arbitration_evidence(decision: dict[str, Any], *, market_id: str, state: str, result: dict[str, Any]) -> None:
    evidence = _dict(decision.get("evidence"))
    payload = {
        "market_id": market_id,
        "state": state,
        "selected_side": result.get("selected_side"),
        "rejected_side": result.get("rejected_side"),
        "winner_side": result.get("selected_side"),
        "outcome": result.get("outcome"),
        "margin": result.get("margin"),
        "required_margin": result.get("required_margin"),
        "tie_breaker_used": result.get("tie_breaker_used"),
        "reason": result.get("reason"),
        "yes_side_evidence_score": result.get("yes_side_evidence_score"),
        "no_side_evidence_score": result.get("no_side_evidence_score"),
        "yes_evidence_quality": result.get("yes_evidence_quality"),
        "no_evidence_quality": result.get("no_evidence_quality"),
        "missing_side_evidence": result.get("missing_side_evidence_json"),
        "source": "same_market_side_arbitrator",
    }
    evidence["same_market_side_arbitration"] = json_safe(payload)
    evidence["same_market_opposing_enter_arbitration"] = json_safe(payload)
    decision["evidence"] = evidence


def _record_arbitration(conn: Any, result: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO same_market_side_arbitrations (
            arbitration_id, paper_session_id, market_id, defense_level,
            yes_decision_id, no_decision_id, yes_score, no_score,
            yes_arbitration_score, no_arbitration_score, selected_side, rejected_side,
            margin, required_margin, tie_breaker_used, outcome, conflict_type,
            ignored_or_softened_conflict, strict_verdict, effective_verdict, reason,
            yes_evidence_json, no_evidence_json, yes_side_evidence_score,
            no_side_evidence_score, yes_evidence_quality, no_evidence_quality,
            side_unknown_count, missing_side_evidence_json, metadata_json
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (arbitration_id) DO NOTHING
        """,
        (
            result.get("arbitration_id"),
            result.get("paper_session_id"),
            result.get("market_id"),
            result.get("defense_level"),
            result.get("yes_decision_id"),
            result.get("no_decision_id"),
            result.get("yes_score"),
            result.get("no_score"),
            result.get("yes_arbitration_score"),
            result.get("no_arbitration_score"),
            result.get("selected_side"),
            result.get("rejected_side"),
            result.get("margin"),
            result.get("required_margin"),
            result.get("tie_breaker_used"),
            result.get("outcome"),
            result.get("conflict_type"),
            bool(result.get("ignored_or_softened_conflict")),
            result.get("strict_verdict"),
            result.get("effective_verdict"),
            result.get("reason"),
            Jsonb(json_safe(result.get("yes_evidence_json") or {})),
            Jsonb(json_safe(result.get("no_evidence_json") or {})),
            result.get("yes_side_evidence_score"),
            result.get("no_side_evidence_score"),
            result.get("yes_evidence_quality"),
            result.get("no_evidence_quality"),
            int(result.get("side_unknown_count") or 0),
            Jsonb(json_safe(result.get("missing_side_evidence_json") or [])),
            Jsonb(json_safe(result.get("metadata_json") or {})),
        ),
    )


def _required_margin(defense_level: int) -> Decimal:
    if defense_level >= 100:
        return Decimal("10")
    if defense_level >= 80:
        return Decimal("8")
    if defense_level >= 60:
        return Decimal("6")
    if defense_level >= 40:
        return Decimal("4")
    if defense_level >= 20:
        return Decimal("2")
    return Decimal("0")


def _bonus(details: dict[str, Any], name: str, value: int | str) -> Decimal:
    amount = Decimal(str(value))
    details["bonuses"][name] = amount
    return amount


def _penalty(details: dict[str, Any], name: str, value: int | str) -> Decimal:
    amount = Decimal(str(value))
    details["penalties"][name] = amount
    return -amount


def _spread(evidence: dict[str, Any]) -> Decimal | None:
    bid = _decimal_or_none(evidence.get("orderbook_best_bid"))
    ask = _decimal_or_none(evidence.get("orderbook_best_ask"))
    if bid is None or ask is None:
        return None
    return abs(ask - bid)


def _liquidity_score(evidence: dict[str, Any], spread: Decimal | None) -> Decimal | None:
    source = _dict(evidence.get("source_evidence"))
    raw = _decimal_or_none(evidence.get("orderbook_liquidity_score") or source.get("orderbook_liquidity_score"))
    if raw is not None:
        return max(Decimal("0"), min(Decimal("1"), raw))
    if spread is None:
        return None
    return max(Decimal("0"), min(Decimal("1"), Decimal("1") - (spread / Decimal("0.20"))))


def _compare_lower(left: Any, right: Any) -> str | None:
    left_decimal = _decimal_or_none(left)
    right_decimal = _decimal_or_none(right)
    if left_decimal is None or right_decimal is None or left_decimal == right_decimal:
        return None
    return "YES" if left_decimal < right_decimal else "NO"


def _compare_higher(left: Any, right: Any) -> str | None:
    left_decimal = _decimal_or_none(left)
    right_decimal = _decimal_or_none(right)
    if left_decimal is None or right_decimal is None or left_decimal == right_decimal:
        return None
    return "YES" if left_decimal > right_decimal else "NO"


def _compare_bonus(yes: SideScore, no: SideScore, *keys: str) -> str | None:
    yes_score = sum(_decimal(yes.evidence.get("bonuses", {}).get(key)) for key in keys)
    no_score = sum(_decimal(no.evidence.get("bonuses", {}).get(key)) for key in keys)
    if yes_score == no_score:
        return None
    return "YES" if yes_score > no_score else "NO"


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _unique(items: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
