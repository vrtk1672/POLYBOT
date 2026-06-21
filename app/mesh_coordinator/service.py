from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.mesh_coordinator.repository import MeshCoordinatorRepository, table_exists
from app.mesh_coordinator.types import MeshFinalAction, MeshFinalStance, MeshSafetyStatus, PROTECTIVE_BRAINS
from app.services.capital_efficiency import CapitalEfficiencyService
from app.services.exit_hold_reasoning import ExitHoldReasoningService
from app.services.payout_odds import PayoutOddsService
from app.services.trade_lifecycle import TradeLifecycleService
from app.services.system_power import SystemPowerService


class MeshCoordinatorBlocked(RuntimeError):
    pass


class MeshCoordinatorDecisionService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: MeshCoordinatorRepository | None = None,
        system_power: SystemPowerService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or MeshCoordinatorRepository()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)

    def judge_session(self, session_id: str) -> dict[str, Any]:
        self._assert_system_on()
        with self._factory.connect() as conn, conn.transaction():
            return self.judge_session_with_conn(conn, session_id)

    def judge_pending_bundles(self, *, limit: int = 100) -> dict[str, Any]:
        self._assert_system_on()
        judged = 0
        with self._factory.connect() as conn, conn.transaction():
            if not self._tables_ready(conn):
                return {"mock_data": False, "status": "MISSING_TABLES", "decisions_judged": 0}
            for bundle in self._repository.list_bundles(conn, limit=limit):
                result = self.judge_session_with_conn(conn, str(bundle["session_id"]))
                judged += int(result.get("status") == "OK")
        return {"mock_data": False, "status": "OK", "decisions_judged": judged}

    def judge_session_with_conn(self, conn: Any, session_id: str) -> dict[str, Any]:
        if not self._tables_ready(conn):
            return {"mock_data": False, "status": "MISSING_TABLES", "session_id": session_id}
        session = self._repository.get_session(conn, session_id)
        bundle = self._repository.get_bundle(conn, session_id)
        if not session or not bundle:
            return {"mock_data": False, "status": "BUNDLE_NOT_FOUND", "session_id": session_id}
        opinions = self._repository.list_opinions(conn, session_id)
        decision, sources, conflicts = self._judge(session=session, bundle=bundle, opinions=opinions)
        row = self._repository.upsert_decision(conn, decision)
        self._repository.replace_sources(conn, decision_id=str(row["decision_id"]), sources=sources)
        self._repository.replace_conflicts(conn, decision_id=str(row["decision_id"]), conflicts=conflicts)
        return {
            "mock_data": False,
            "status": "OK",
            "session_id": session_id,
            "decision_id": row["decision_id"],
            "final_stance": row["final_stance"],
            "final_action": row["final_action"],
            "source_brain_count": row["source_brain_count"],
            "conflicts_detected": row["conflicts_detected"],
            "conflict_count": row["conflict_count"],
        }

    def dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard("DB_UNAVAILABLE")
        with self._factory.connect() as conn:
            if not self._tables_ready(conn):
                return _empty_dashboard("MISSING_TABLES")
            latest = self._repository.dashboard_rows(conn, limit=limit)
            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(AVG(source_brain_count), 0) AS avg_source_brain_count,
                    COUNT(*) FILTER (WHERE conflicts_detected IS TRUE) AS conflicts_detected_count
                FROM mesh_coordinator_decisions
                """
            ).fetchone()
            by_stance = conn.execute(
                """
                SELECT final_stance, COUNT(*) AS count
                FROM mesh_coordinator_decisions
                GROUP BY final_stance
                ORDER BY count DESC, final_stance
                """
            ).fetchall()
            by_action = conn.execute(
                """
                SELECT final_action, COUNT(*) AS count
                FROM mesh_coordinator_decisions
                GROUP BY final_action
                ORDER BY count DESC, final_action
                """
            ).fetchall()
            conflict_types = conn.execute(
                """
                SELECT conflict_type, COUNT(*) AS count
                FROM mesh_conflict_records
                GROUP BY conflict_type
                ORDER BY count DESC, conflict_type
                """
            ).fetchall()
            source_distribution = conn.execute(
                """
                SELECT source_brain_count, COUNT(*) AS count
                FROM mesh_coordinator_decisions
                GROUP BY source_brain_count
                ORDER BY source_brain_count
                """
            ).fetchall()
            safety = conn.execute(
                """
                SELECT safety_status, COUNT(*) AS count
                FROM mesh_coordinator_decisions
                GROUP BY safety_status
                ORDER BY safety_status
                """
            ).fetchall()
            payout_odds = PayoutOddsService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
            exit_hold = ExitHoldReasoningService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
            capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
            trade_lifecycle = TradeLifecycleService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
        return {
            "mock_data": False,
            "status": "OK",
            "generated_at": datetime.now(UTC).isoformat(),
            "total_mesh_decisions": int(totals["total"] or 0),
            "decisions_by_final_stance": {str(row["final_stance"]): int(row["count"] or 0) for row in by_stance},
            "decisions_by_final_action": {str(row["final_action"]): int(row["count"] or 0) for row in by_action},
            "avg_source_brain_count": round(float(totals["avg_source_brain_count"] or 0), 4),
            "conflicts_detected_count": int(totals["conflicts_detected_count"] or 0),
            "conflict_types": {str(row["conflict_type"]): int(row["count"] or 0) for row in conflict_types},
            "latest_decisions": [_json_safe(row) for row in latest],
            "safety_status": {str(row["safety_status"]): int(row["count"] or 0) for row in safety},
            "source_brain_count_distribution": {str(row["source_brain_count"]): int(row["count"] or 0) for row in source_distribution},
            "payout_odds_visibility": payout_odds,
            "payout_odds_observational_only": True,
            "exit_hold_visibility": exit_hold,
            "exit_hold_observational_only": True,
            "capital_efficiency_visibility": capital_efficiency,
            "capital_efficiency_observational_only": True,
            "trade_lifecycle_visibility": trade_lifecycle,
            "trade_lifecycle_observational_only": True,
        }

    def detail(self, decision_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DB_UNAVAILABLE", "decision_id": decision_id}
        with self._factory.connect() as conn:
            if not self._tables_ready(conn):
                return {"mock_data": False, "status": "MISSING_TABLES", "decision_id": decision_id}
            payload = self._repository.detail(conn, decision_id)
            payout_odds = None
            if payload:
                decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else payload
                payout_odds = PayoutOddsService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(decision.get("market_id")) if decision.get("market_id") else None,
                    position_id=str(decision.get("position_id")) if decision.get("position_id") else None,
                )
                exit_hold = ExitHoldReasoningService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(decision.get("market_id")) if decision.get("market_id") else None,
                    position_id=str(decision.get("position_id")) if decision.get("position_id") else None,
                )
                capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(decision.get("market_id")) if decision.get("market_id") else None,
                    position_id=str(decision.get("position_id")) if decision.get("position_id") else None,
                )
                trade_lifecycle = TradeLifecycleService(connection_factory=self._factory).observational_summary_for_market(
                    conn,
                    market_id=str(decision.get("market_id")) if decision.get("market_id") else None,
                    position_id=str(decision.get("position_id")) if decision.get("position_id") else None,
                    candidate_id=str(decision.get("candidate_id")) if decision.get("candidate_id") else None,
                )
            else:
                exit_hold = None
                capital_efficiency = None
                trade_lifecycle = None
        if payload is None:
            return {"mock_data": False, "status": "NOT_FOUND", "decision_id": decision_id}
        payload["payout_odds_visibility"] = payout_odds
        payload["payout_odds_observational_only"] = True
        payload["exit_hold_visibility"] = exit_hold
        payload["exit_hold_observational_only"] = True
        payload["capital_efficiency_visibility"] = capital_efficiency
        payload["capital_efficiency_observational_only"] = True
        payload["trade_lifecycle_visibility"] = trade_lifecycle
        payload["trade_lifecycle_observational_only"] = True
        payload.update({"mock_data": False, "status": "OK", "generated_at": datetime.now(UTC).isoformat()})
        return _json_safe(payload)

    def latest_for_session(self, session_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DB_UNAVAILABLE", "session_id": session_id}
        with self._factory.connect() as conn:
            if not self._tables_ready(conn):
                return {"mock_data": False, "status": "MISSING_TABLES", "session_id": session_id}
            row = self._repository.latest_decision_for_session(conn, session_id)
            if not row:
                return {"mock_data": False, "status": "NOT_FOUND", "session_id": session_id}
            payload = self._repository.detail(conn, str(row["decision_id"]))
            decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else payload
            payout_odds = PayoutOddsService(connection_factory=self._factory).observational_summary_for_market(
                conn,
                market_id=str(decision.get("market_id")) if decision.get("market_id") else None,
                position_id=str(decision.get("position_id")) if decision.get("position_id") else None,
            )
            exit_hold = ExitHoldReasoningService(connection_factory=self._factory).observational_summary_for_market(
                conn,
                market_id=str(decision.get("market_id")) if decision.get("market_id") else None,
                position_id=str(decision.get("position_id")) if decision.get("position_id") else None,
            )
            capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).observational_summary_for_market(
                conn,
                market_id=str(decision.get("market_id")) if decision.get("market_id") else None,
                position_id=str(decision.get("position_id")) if decision.get("position_id") else None,
            )
            trade_lifecycle = TradeLifecycleService(connection_factory=self._factory).observational_summary_for_market(
                conn,
                market_id=str(decision.get("market_id")) if decision.get("market_id") else None,
                position_id=str(decision.get("position_id")) if decision.get("position_id") else None,
                candidate_id=str(decision.get("candidate_id")) if decision.get("candidate_id") else None,
            )
        payload["payout_odds_visibility"] = payout_odds
        payload["payout_odds_observational_only"] = True
        payload["exit_hold_visibility"] = exit_hold
        payload["exit_hold_observational_only"] = True
        payload["capital_efficiency_visibility"] = capital_efficiency
        payload["capital_efficiency_observational_only"] = True
        payload["trade_lifecycle_visibility"] = trade_lifecycle
        payload["trade_lifecycle_observational_only"] = True
        payload.update({"mock_data": False, "status": "OK", "generated_at": datetime.now(UTC).isoformat()})
        return _json_safe(payload)

    def _judge(
        self,
        *,
        session: dict[str, Any],
        bundle: dict[str, Any],
        opinions: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        opinion_by_brain = {str(opinion["brain_type"]): opinion for opinion in opinions}
        source_brain_count = int(bundle.get("source_brain_count") or len(opinion_by_brain))
        opinion_count = int(bundle.get("opinion_count") or len(opinions))
        conflicts = _detect_conflicts(session=session, bundle=bundle, opinions=opinions)
        judgment = _arbitrate(session=session, opinions=opinions, conflicts=conflicts)
        supporting = [opinion for opinion in opinions if opinion.get("stance") in {"SUPPORT", "CAUTION"}]
        opposing = [opinion for opinion in opinions if opinion.get("stance") == "BLOCK"]
        decision_id = f"mesh_decision_{session['session_id']}"
        confidence = _decision_confidence(opinions, judgment["final_stance"])
        decision = {
            "decision_id": decision_id,
            "session_id": session["session_id"],
            "bundle_id": bundle["bundle_id"],
            "market_id": bundle.get("market_id") or session.get("market_id"),
            "candidate_id": bundle.get("candidate_id") or session.get("candidate_id"),
            "position_id": bundle.get("position_id") or session.get("position_id"),
            "final_stance": judgment["final_stance"],
            "final_action": judgment["final_action"],
            "confidence": confidence,
            "source_brain_count": source_brain_count,
            "opinion_count": opinion_count,
            "conflicts_detected": bool(conflicts),
            "conflict_count": len(conflicts),
            "winning_brains_json": judgment["winning_brains"],
            "losing_brains_json": judgment["losing_brains"],
            "supporting_opinions_json": [_opinion_ref(opinion) for opinion in supporting],
            "opposing_opinions_json": [_opinion_ref(opinion) for opinion in opposing],
            "decision_reason": judgment["decision_reason"],
            "safety_status": judgment["safety_status"],
            "coordinator_ready": bool(bundle.get("coordinator_ready")) and source_brain_count > 1,
        }
        sources = [
            {
                "opinion_id": opinion["opinion_id"],
                "brain_name": opinion["brain_name"],
                "brain_type": opinion["brain_type"],
                "stance": opinion["stance"],
                "confidence": float(opinion.get("confidence") or 0),
                "influence": _source_influence(opinion, judgment),
                "contribution_summary": f"{opinion['brain_name']} produced {opinion['stance']}: {opinion.get('reasoning_summary')}",
            }
            for opinion in opinions
        ]
        for conflict in conflicts:
            conflict["decision_id"] = decision_id
        return decision, sources, conflicts

    def _tables_ready(self, conn: Any) -> bool:
        return all(
            table_exists(conn, table)
            for table in (
                "mesh_brain_opinions",
                "mesh_coordinator_input_bundles",
                "mesh_coordinator_decisions",
                "mesh_coordinator_decision_sources",
                "mesh_conflict_records",
            )
        )

    def _assert_system_on(self) -> None:
        power = self._system_power.get_power_state()
        if str(power.get("power") or "OFF").upper() != "ON" or not power.get("runtime_work_allowed"):
            raise MeshCoordinatorBlocked("SYSTEM_POWER_OFF")


def _arbitrate(*, session: dict[str, Any], opinions: list[dict[str, Any]], conflicts: list[dict[str, Any]]) -> dict[str, Any]:
    by_brain = {str(opinion["brain_type"]): opinion for opinion in opinions}
    stances = {brain: str(opinion.get("stance") or "NO_SIGNAL") for brain, opinion in by_brain.items()}
    no_signal_count = len([stance for stance in stances.values() if stance == "NO_SIGNAL"])
    support_count = len([stance for stance in stances.values() if stance == "SUPPORT"])
    block_count = len([stance for stance in stances.values() if stance == "BLOCK"])
    position_session = bool(session.get("position_id")) or session.get("session_type") == "POSITION_SESSION"

    risk = by_brain.get("RISK_BRAIN")
    capital = by_brain.get("CAPITAL_BRAIN")
    exit_opinion = by_brain.get("EXIT_BRAIN")
    context = by_brain.get("CONTEXT_BRAIN")
    position = by_brain.get("POSITION_BRAIN")

    if risk and risk.get("stance") == "BLOCK":
        return _judgment(
            MeshFinalStance.BLOCK,
            MeshFinalAction.BLOCK,
            "Risk BLOCK beats all supporting opinions.",
            winners=[risk],
            losers=_supporting_opinions(opinions),
            safety=MeshSafetyStatus.BLOCKED_NON_EXECUTING,
        )
    if capital and capital.get("stance") == "BLOCK":
        return _judgment(
            MeshFinalStance.BLOCK,
            MeshFinalAction.BLOCK,
            "Capital BLOCK beats trade support and prevents candidate approval.",
            winners=[capital],
            losers=_supporting_opinions(opinions),
            safety=MeshSafetyStatus.BLOCKED_NON_EXECUTING,
        )
    if exit_opinion and exit_opinion.get("stance") == "BLOCK":
        return _judgment(
            MeshFinalStance.BLOCK,
            MeshFinalAction.BLOCK,
            "Exit BLOCK blocks entry interpretation.",
            winners=[exit_opinion],
            losers=_supporting_opinions(opinions),
            safety=MeshSafetyStatus.BLOCKED_NON_EXECUTING,
        )
    if position_session and exit_opinion and exit_opinion.get("stance") in {"CAUTION", "BLOCK"} and risk and risk.get("stance") in {"CAUTION", "BLOCK"}:
        return _judgment(
            MeshFinalStance.EXIT_RECOMMENDED,
            MeshFinalAction.EXIT_REVIEW,
            "Position session has adverse exit/risk context; route to exit review only.",
            winners=[opinion for opinion in (exit_opinion, risk) if opinion],
            losers=_supporting_opinions(opinions, exclude={"EXIT_BRAIN", "RISK_BRAIN"}),
            safety=MeshSafetyStatus.SAFE_NON_EXECUTING,
        )
    if position_session and position and position.get("stance") == "CAUTION":
        protective = [opinion for opinion in (position, risk, exit_opinion, capital) if opinion and opinion.get("stance") in {"CAUTION", "BLOCK"}]
        return _judgment(
            MeshFinalStance.EXIT_WATCH,
            MeshFinalAction.EXIT_REVIEW if len(protective) > 1 else MeshFinalAction.WATCH,
            "Living position awareness found adverse context; coordinator keeps this non-executing and visible for review.",
            winners=protective or [position],
            losers=_supporting_opinions(opinions, exclude={str(opinion.get("brain_type")) for opinion in protective}),
            safety=MeshSafetyStatus.SAFE_NON_EXECUTING,
        )
    if not opinions or no_signal_count > len(opinions) / 2:
        return _judgment(
            MeshFinalStance.INSUFFICIENT_DATA,
            MeshFinalAction.INSUFFICIENT_DATA,
            "Most source brains produced NO_SIGNAL; mesh decision remains insufficient data.",
            winners=[],
            losers=[],
            safety=MeshSafetyStatus.INSUFFICIENT_DATA,
        )
    if context and context.get("stance") == "SUPPORT" and support_count == 1:
        return _judgment(
            MeshFinalStance.INSUFFICIENT_DATA,
            MeshFinalAction.INSUFFICIENT_DATA,
            "Context SUPPORT alone cannot approve trade review.",
            winners=[context],
            losers=[],
            safety=MeshSafetyStatus.INSUFFICIENT_DATA,
        )
    if risk and capital and exit_opinion and risk.get("stance") == "CAUTION" and capital.get("stance") == "SUPPORT" and exit_opinion.get("stance") == "SUPPORT":
        return _judgment(
            MeshFinalStance.WATCH,
            MeshFinalAction.WATCH,
            "Risk CAUTION with Capital and Exit SUPPORT resolves to WATCH.",
            winners=[risk, capital, exit_opinion],
            losers=[],
            safety=MeshSafetyStatus.SAFE_NON_EXECUTING,
        )
    key_brains = [opinion for opinion in (risk, capital, exit_opinion) if opinion]
    if len(key_brains) >= 3 and all(opinion.get("stance") == "SUPPORT" for opinion in key_brains):
        return _judgment(
            MeshFinalStance.STRONG_SUPPORT if support_count >= 3 else MeshFinalStance.SUPPORT,
            MeshFinalAction.PAPER_CANDIDATE_REVIEW,
            "All key protective brains SUPPORT; coordinator allows paper candidate review only.",
            winners=key_brains,
            losers=[],
            safety=MeshSafetyStatus.SAFE_NON_EXECUTING,
        )
    if position_session and position and position.get("stance") == "SUPPORT" and block_count == 0:
        return _judgment(
            MeshFinalStance.EXIT_WATCH,
            MeshFinalAction.HOLD_REVIEW,
            "Position session has no blocking adverse signal; hold review only.",
            winners=[position],
            losers=[],
            safety=MeshSafetyStatus.SAFE_NON_EXECUTING,
        )
    if block_count:
        blockers = [opinion for opinion in opinions if opinion.get("stance") == "BLOCK"]
        return _judgment(
            MeshFinalStance.BLOCK,
            MeshFinalAction.BLOCK,
            "One or more source brains BLOCK; coordinator remains non-executing and blocks entry interpretation.",
            winners=blockers,
            losers=_supporting_opinions(opinions),
            safety=MeshSafetyStatus.BLOCKED_NON_EXECUTING,
        )
    if conflicts:
        return _judgment(
            MeshFinalStance.WATCH,
            MeshFinalAction.WATCH,
            "Brain opinions disagree without a hard BLOCK; coordinator resolves to WATCH.",
            winners=[opinion for opinion in opinions if opinion.get("brain_type") in PROTECTIVE_BRAINS],
            losers=[],
            safety=MeshSafetyStatus.SAFE_NON_EXECUTING,
        )
    return _judgment(
        MeshFinalStance.WATCH,
        MeshFinalAction.WATCH,
        "Coordinator conservative default: watch and gather more mesh evidence.",
        winners=_supporting_opinions(opinions),
        losers=[],
        safety=MeshSafetyStatus.SAFE_NON_EXECUTING,
    )


def _detect_conflicts(*, session: dict[str, Any], bundle: dict[str, Any], opinions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    supports = [opinion for opinion in opinions if opinion.get("stance") == "SUPPORT"]
    blocks = [opinion for opinion in opinions if opinion.get("stance") == "BLOCK"]
    cautions = [opinion for opinion in opinions if opinion.get("stance") == "CAUTION"]
    index = 0
    for support in supports:
        for block in blocks:
            index += 1
            winner, resolution = _conflict_winner(support, block)
            conflicts.append(_conflict_row(session, bundle, index, "support_vs_block", support, block, 0.9, resolution, winner))
    for caution in cautions:
        for support in supports:
            if caution.get("brain_type") in PROTECTIVE_BRAINS and support.get("brain_type") not in {caution.get("brain_type")}:
                index += 1
                resolution = "Protective caution wins by forcing WATCH."
                conflicts.append(_conflict_row(session, bundle, index, "caution_vs_support", caution, support, 0.45, resolution, str(caution.get("brain_type"))))
    return conflicts


def _conflict_winner(left: dict[str, Any], right: dict[str, Any]) -> tuple[str, str]:
    for opinion in (left, right):
        brain = str(opinion.get("brain_type"))
        stance = str(opinion.get("stance"))
        if brain == "RISK_BRAIN" and stance == "BLOCK":
            return brain, "Risk BLOCK wins by hard safety rule."
        if brain == "CAPITAL_BRAIN" and stance == "BLOCK":
            return brain, "Capital BLOCK wins by hard safety rule."
        if brain == "EXIT_BRAIN" and stance == "BLOCK":
            return brain, "Exit BLOCK wins by hard safety rule."
    blockers = [opinion for opinion in (left, right) if opinion.get("stance") == "BLOCK"]
    if blockers:
        return str(blockers[0].get("brain_type")), "BLOCK stance wins over SUPPORT."
    return str(left.get("brain_type")), "Protective stance wins."


def _conflict_row(
    session: dict[str, Any],
    bundle: dict[str, Any],
    index: int,
    conflict_type: str,
    a: dict[str, Any],
    b: dict[str, Any],
    severity: float,
    resolution: str,
    winner: str,
) -> dict[str, Any]:
    return {
        "conflict_id": f"mesh_conflict_{session['session_id']}_{index}",
        "session_id": session["session_id"],
        "bundle_id": bundle["bundle_id"],
        "conflict_type": conflict_type,
        "brain_a": str(a.get("brain_type")),
        "stance_a": str(a.get("stance")),
        "brain_b": str(b.get("brain_type")),
        "stance_b": str(b.get("stance")),
        "severity": severity,
        "resolution": resolution,
        "winner": winner,
        "reason": f"{a.get('brain_name')} {a.get('stance')} vs {b.get('brain_name')} {b.get('stance')}. {resolution}",
    }


def _judgment(
    final_stance: MeshFinalStance,
    final_action: MeshFinalAction,
    reason: str,
    *,
    winners: list[dict[str, Any]],
    losers: list[dict[str, Any]],
    safety: MeshSafetyStatus,
) -> dict[str, Any]:
    return {
        "final_stance": final_stance.value,
        "final_action": final_action.value,
        "decision_reason": reason,
        "winning_brains": [_opinion_ref(opinion) for opinion in winners],
        "losing_brains": [_opinion_ref(opinion) for opinion in losers],
        "safety_status": safety.value,
    }


def _opinion_ref(opinion: dict[str, Any]) -> dict[str, Any]:
    return {
        "opinion_id": opinion.get("opinion_id"),
        "brain_name": opinion.get("brain_name"),
        "brain_type": opinion.get("brain_type"),
        "stance": opinion.get("stance"),
        "confidence": float(opinion.get("confidence") or 0),
    }


def _supporting_opinions(opinions: list[dict[str, Any]], *, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    exclude = exclude or set()
    return [opinion for opinion in opinions if opinion.get("stance") == "SUPPORT" and opinion.get("brain_type") not in exclude]


def _source_influence(opinion: dict[str, Any], judgment: dict[str, Any]) -> str:
    brain_type = str(opinion.get("brain_type"))
    winners = {str(item.get("brain_type")) for item in judgment.get("winning_brains") or []}
    losers = {str(item.get("brain_type")) for item in judgment.get("losing_brains") or []}
    if brain_type in winners:
        return "WINNER"
    if brain_type in losers:
        return "LOSER"
    if opinion.get("stance") == "BLOCK":
        return "OPPOSING"
    if opinion.get("stance") in {"SUPPORT", "CAUTION"}:
        return "SUPPORTING"
    return "CONTEXT"


def _decision_confidence(opinions: list[dict[str, Any]], final_stance: str) -> float:
    if not opinions:
        return 0.0
    values = [float(opinion.get("confidence") or 0) for opinion in opinions]
    average = sum(values) / len(values)
    if final_stance == MeshFinalStance.INSUFFICIENT_DATA.value:
        return round(min(0.4, average), 4)
    return round(max(0.0, min(1.0, average)), 4)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _empty_dashboard(status: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "total_mesh_decisions": 0,
        "decisions_by_final_stance": {},
        "decisions_by_final_action": {},
        "avg_source_brain_count": 0.0,
        "conflicts_detected_count": 0,
        "conflict_types": {},
        "latest_decisions": [],
        "safety_status": {},
        "source_brain_count_distribution": {},
    }
