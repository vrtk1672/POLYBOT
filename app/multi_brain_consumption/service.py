from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.multi_brain_consumption.repository import MultiBrainConsumptionRepository, table_exists
from app.multi_brain_consumption.types import BRAIN_SPECS, OPINION_BRAIN_TYPES, BrainSpec, BrainStance, BrainType
from app.services.system_power import SystemPowerService
from app.shared_awareness.types import ALL_DOMAINS, DOMAIN_STATE_COLUMNS, AwarenessDomain


class MultiBrainConsumptionBlocked(RuntimeError):
    pass


class MultiBrainConsumptionService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: MultiBrainConsumptionRepository | None = None,
        system_power: SystemPowerService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or MultiBrainConsumptionRepository()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)

    def consume_session(self, session_id: str) -> dict[str, Any]:
        self._assert_system_on()
        with self._factory.connect() as conn, conn.transaction():
            return self.consume_session_with_conn(conn, session_id)

    def consume_active_sessions(self, *, limit: int = 100) -> dict[str, Any]:
        self._assert_system_on()
        consumed = 0
        with self._factory.connect() as conn, conn.transaction():
            if not self._tables_ready(conn):
                return {"mock_data": False, "status": "MISSING_TABLES", "sessions_consumed": 0}
            for session_id in self._repository.list_awareness_sessions(conn, limit=limit):
                result = self.consume_session_with_conn(conn, session_id)
                consumed += int(result.get("status") == "OK")
        return {"mock_data": False, "status": "OK", "sessions_consumed": consumed}

    def consume_session_with_conn(self, conn: Any, session_id: str) -> dict[str, Any]:
        if not self._tables_ready(conn):
            return {"mock_data": False, "status": "MISSING_TABLES", "session_id": session_id}
        session = self._repository.get_session(conn, session_id)
        awareness = self._repository.get_awareness(conn, session_id)
        if not session or not awareness:
            return {"mock_data": False, "status": "AWARENESS_NOT_FOUND", "session_id": session_id}
        sources = self._repository.awareness_sources(conn, str(awareness["awareness_id"]))
        capital_evaluation = self._repository.latest_capital_evaluation(conn, session_id)
        position_awareness = self._repository.latest_position_awareness(conn, session_id)
        domain_states = _domain_states(awareness)
        opinions: list[dict[str, Any]] = []
        for brain_type in OPINION_BRAIN_TYPES:
            spec = BRAIN_SPECS[brain_type]
            if brain_type == BrainType.POSITION_BRAIN and not (_position_brain_applicable(session, domain_states) or position_awareness):
                self._repository.delete_position_opinion_if_not_applicable(conn, session_id)
                continue
            opinion, opinion_sources = self._build_opinion(
                session,
                awareness,
                domain_states,
                sources,
                spec,
                capital_evaluation=capital_evaluation,
                position_awareness=position_awareness,
            )
            row = self._repository.upsert_opinion(conn, opinion)
            self._repository.replace_sources(
                conn,
                opinion_id=str(row["opinion_id"]),
                session_id=session_id,
                sources=opinion_sources,
            )
            opinions.append(dict(row))
        bundle = self._build_bundle(session, opinions)
        bundle_row = self._repository.upsert_bundle(conn, bundle)
        observer, observer_sources = self._build_observer_opinion(session, opinions, dict(bundle_row))
        observer_row = self._repository.upsert_opinion(conn, observer)
        self._repository.replace_sources(
            conn,
            opinion_id=str(observer_row["opinion_id"]),
            session_id=session_id,
            sources=observer_sources,
        )
        mesh_decision_id = None
        if table_exists(conn, "mesh_coordinator_decisions"):
            from app.mesh_coordinator.service import MeshCoordinatorDecisionService

            mesh_decision = MeshCoordinatorDecisionService(connection_factory=self._factory).judge_session_with_conn(conn, session_id)
            mesh_decision_id = mesh_decision.get("decision_id")
        return {
            "mock_data": False,
            "status": "OK",
            "session_id": session_id,
            "opinions_created_or_updated": len(opinions) + 1,
            "source_brain_count": bundle_row["source_brain_count"],
            "conflicts_detected": bundle_row["conflicts_detected"],
            "conflict_count": bundle_row["conflict_count"],
            "mesh_decision_id": mesh_decision_id,
        }

    def dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard("DB_UNAVAILABLE")
        with self._factory.connect() as conn:
            if not self._tables_ready(conn):
                return _empty_dashboard("MISSING_TABLES")
            bundles = self._repository.dashboard_rows(conn, limit=limit)
            totals = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT session_id) AS sessions_with_opinions,
                    COUNT(*) AS total_opinions
                FROM mesh_brain_opinions
                WHERE brain_type <> 'COORDINATOR_OBSERVER'
                """
            ).fetchone()
            bundle_stats = conn.execute(
                """
                SELECT
                    COALESCE(AVG(source_brain_count), 0) AS avg_source_brain_count,
                    COUNT(*) FILTER (WHERE source_brain_count > 1) AS sessions_gt_one,
                    COUNT(*) FILTER (WHERE conflicts_detected IS TRUE) AS conflicts_detected_count
                FROM mesh_coordinator_input_bundles
                """
            ).fetchone()
            participation = conn.execute(
                """
                SELECT brain_type, COUNT(*) AS count
                FROM mesh_brain_opinions
                GROUP BY brain_type
                ORDER BY brain_type
                """
            ).fetchall()
            missing_rows = conn.execute(
                """
                SELECT missing_domains_json
                FROM mesh_brain_opinions
                WHERE brain_type <> 'COORDINATOR_OBSERVER'
                """
            ).fetchall()
        return {
            "mock_data": False,
            "status": "OK",
            "generated_at": datetime.now(UTC).isoformat(),
            "total_sessions_with_opinions": int(totals["sessions_with_opinions"] or 0),
            "total_brain_opinions": int(totals["total_opinions"] or 0),
            "avg_source_brain_count": round(float(bundle_stats["avg_source_brain_count"] or 0), 4),
            "sessions_with_source_brain_count_gt_1": int(bundle_stats["sessions_gt_one"] or 0),
            "conflicts_detected_count": int(bundle_stats["conflicts_detected_count"] or 0),
            "brain_participation_by_type": {str(row["brain_type"]): int(row["count"] or 0) for row in participation},
            "missing_domain_counts": _missing_domain_counts(missing_rows),
            "latest_bundles": [_json_safe(row) for row in bundles],
        }

    def detail(self, session_id: str, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DB_UNAVAILABLE", "session_id": session_id}
        with self._factory.connect() as conn:
            if not self._tables_ready(conn):
                return {"mock_data": False, "status": "MISSING_TABLES", "session_id": session_id}
            payload = self._repository.detail(conn, session_id, limit=limit)
        if payload is None:
            return {"mock_data": False, "status": "NOT_FOUND", "session_id": session_id}
        payload.update({"mock_data": False, "status": "OK", "generated_at": datetime.now(UTC).isoformat()})
        return _json_safe(payload)

    def _build_opinion(
        self,
        session: dict[str, Any],
        awareness: dict[str, Any],
        domain_states: dict[AwarenessDomain, dict[str, Any]],
        sources: list[dict[str, Any]],
        spec: BrainSpec,
        capital_evaluation: dict[str, Any] | None = None,
        position_awareness: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        consumed = [domain.value for domain in spec.consumed_domains]
        missing = [
            domain.value
            for domain in spec.consumed_domains
            if domain_states[domain].get("status") == "MISSING"
        ]
        stale = [
            domain.value
            for domain in spec.consumed_domains
            if domain_states[domain].get("status") == "STALE"
        ]
        present_domains = [
            domain.value
            for domain in spec.consumed_domains
            if int(domain_states[domain].get("source_count") or 0) > 0
        ]
        support_refs, oppose_refs, opinion_sources = _source_refs_for_domains(domain_states, sources, spec.consumed_domains)
        stance, bias, reason = _stance_for_spec(spec, domain_states, session, capital_evaluation=capital_evaluation, position_awareness=position_awareness)
        if spec.brain_type == BrainType.CAPITAL_BRAIN and capital_evaluation:
            present_domains = list(dict.fromkeys([*present_domains, "CAPITAL_BRAIN_EVALUATION"]))
            evaluation_ref = {
                "source_domain": "CAPITAL_BRAIN_EVALUATION",
                "source_table": "capital_brain_evaluations",
                "source_record_id": str(capital_evaluation["evaluation_id"]),
                "source_status": "PRESENT",
                "summary": f"upstream capital decision={capital_evaluation.get('decision')}",
            }
            support_refs = [evaluation_ref, *support_refs]
            opinion_sources = [
                {
                    "source_domain": "CAPITAL_BRAIN_EVALUATION",
                    "source_table": "capital_brain_evaluations",
                    "source_record_id": str(capital_evaluation["evaluation_id"]),
                    "source_status": "PRESENT",
                    "influence": "OPPOSING" if capital_evaluation.get("decision") == "CAPITAL_BLOCK" else "SUPPORTING",
                    "contribution_summary": str(capital_evaluation.get("reason") or "upstream capital evaluation"),
                },
                *opinion_sources,
            ]
        if spec.brain_type == BrainType.POSITION_BRAIN and position_awareness:
            present_domains = list(dict.fromkeys([*present_domains, "POSITION_AWARENESS"]))
            awareness_ref = {
                "source_domain": "POSITION_AWARENESS",
                "source_table": "position_awareness",
                "source_record_id": str(position_awareness["awareness_id"]),
                "source_status": "PRESENT",
                "summary": f"position awareness risk={position_awareness.get('risk_status')} exit={position_awareness.get('exit_status')} capital={position_awareness.get('capital_status')}",
            }
            support_refs = [awareness_ref, *support_refs]
            influence = "OPPOSING" if _position_awareness_adverse(position_awareness) else "SUPPORTING"
            opinion_sources = [
                {
                    "source_domain": "POSITION_AWARENESS",
                    "source_table": "position_awareness",
                    "source_record_id": str(position_awareness["awareness_id"]),
                    "source_status": "PRESENT",
                    "influence": influence,
                    "contribution_summary": f"position awareness score={position_awareness.get('awareness_score')}",
                },
                *opinion_sources,
            ]
        confidence = _opinion_confidence(spec, domain_states, stance)
        if spec.brain_type == BrainType.CAPITAL_BRAIN and capital_evaluation:
            confidence = round(max(confidence, float(capital_evaluation.get("confidence") or 0)), 4)
        if spec.brain_type == BrainType.POSITION_BRAIN and position_awareness:
            confidence = round(max(confidence, float(position_awareness.get("awareness_score") or 0)), 4)
        opinion_id = f"mesh_opinion_{session['session_id']}_{spec.brain_type.value.lower()}"
        return (
            {
                "opinion_id": opinion_id,
                "session_id": session["session_id"],
                "brain_name": spec.brain_name,
                "brain_type": spec.brain_type.value,
                "market_id": awareness.get("market_id"),
                "candidate_id": awareness.get("candidate_id"),
                "position_id": awareness.get("position_id"),
                "stance": stance.value,
                "confidence": confidence,
                "decision_bias": bias,
                "reasoning_summary": reason,
                "consumed_domains_json": present_domains,
                "missing_domains_json": missing,
                "stale_domains_json": stale,
                "supporting_sources_json": support_refs,
                "opposing_sources_json": oppose_refs,
                "conflicts_json": [],
            },
            opinion_sources,
        )

    def _build_bundle(self, session: dict[str, Any], opinions: list[dict[str, Any]]) -> dict[str, Any]:
        brain_opinions = [opinion for opinion in opinions if opinion["brain_type"] != BrainType.COORDINATOR_OBSERVER.value]
        conflicts = _detect_conflicts(brain_opinions)
        stance_counts = Counter(str(opinion.get("stance") or "NO_SIGNAL") for opinion in brain_opinions)
        stance_summary = {
            "counts": dict(stance_counts),
            "by_brain": [
                {
                    "brain_type": opinion.get("brain_type"),
                    "brain_name": opinion.get("brain_name"),
                    "stance": opinion.get("stance"),
                    "confidence": float(opinion.get("confidence") or 0),
                }
                for opinion in brain_opinions
            ],
            "conflicts": conflicts,
        }
        source_brain_count = len({opinion["brain_type"] for opinion in brain_opinions})
        return {
            "bundle_id": f"mesh_coordinator_bundle_{session['session_id']}",
            "session_id": session["session_id"],
            "market_id": session.get("market_id"),
            "candidate_id": session.get("candidate_id"),
            "position_id": session.get("position_id"),
            "source_brain_count": source_brain_count,
            "opinion_count": len(brain_opinions),
            "stance_summary_json": stance_summary,
            "conflicts_detected": bool(conflicts),
            "conflict_count": len(conflicts),
            "coordinator_ready": source_brain_count > 1,
        }

    def _build_observer_opinion(
        self,
        session: dict[str, Any],
        opinions: list[dict[str, Any]],
        bundle: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        conflicts = (bundle.get("stance_summary_json") or {}).get("conflicts") or []
        stance = BrainStance.CAUTION if conflicts else BrainStance.SUPPORT if int(bundle.get("source_brain_count") or 0) > 1 else BrainStance.NO_SIGNAL
        reason = (
            f"Collected {bundle.get('source_brain_count')} source brains and {bundle.get('opinion_count')} opinions."
        )
        if conflicts:
            reason += f" Conflict detected: {conflicts[0].get('summary')}"
        opinion_id = f"mesh_opinion_{session['session_id']}_{BrainType.COORDINATOR_OBSERVER.value.lower()}"
        source_refs = [
            {
                "opinion_id": opinion.get("opinion_id"),
                "brain_type": opinion.get("brain_type"),
                "stance": opinion.get("stance"),
            }
            for opinion in opinions
        ]
        opinion_sources = [
            {
                "source_domain": "BRAIN_OPINION",
                "source_table": "mesh_brain_opinions",
                "source_record_id": str(opinion.get("opinion_id")),
                "source_status": "PRESENT",
                "influence": "CONTEXT",
                "contribution_summary": f"{opinion.get('brain_name')} produced {opinion.get('stance')}",
            }
            for opinion in opinions
        ]
        return (
            {
                "opinion_id": opinion_id,
                "session_id": session["session_id"],
                "brain_name": "Coordinator Observer",
                "brain_type": BrainType.COORDINATOR_OBSERVER.value,
                "market_id": session.get("market_id"),
                "candidate_id": session.get("candidate_id"),
                "position_id": session.get("position_id"),
                "stance": stance.value,
                "confidence": 0.7 if opinions else 0.0,
                "decision_bias": "OBSERVE",
                "reasoning_summary": reason,
                "consumed_domains_json": ["BRAIN_OPINIONS"],
                "missing_domains_json": [],
                "stale_domains_json": [],
                "supporting_sources_json": source_refs,
                "opposing_sources_json": conflicts,
                "conflicts_json": conflicts,
            },
            opinion_sources,
        )

    def _tables_ready(self, conn: Any) -> bool:
        return all(
            table_exists(conn, table)
            for table in (
                "mesh_shared_awareness",
                "mesh_awareness_sources",
                "mesh_brain_opinions",
                "mesh_brain_consumption_sources",
                "mesh_coordinator_input_bundles",
            )
        )

    def _assert_system_on(self) -> None:
        power = self._system_power.get_power_state()
        if str(power.get("power") or "OFF").upper() != "ON" or not power.get("runtime_work_allowed"):
            raise MultiBrainConsumptionBlocked("SYSTEM_POWER_OFF")


def _stance_for_spec(
    spec: BrainSpec,
    domain_states: dict[AwarenessDomain, dict[str, Any]],
    session: dict[str, Any],
    *,
    capital_evaluation: dict[str, Any] | None = None,
    position_awareness: dict[str, Any] | None = None,
) -> tuple[BrainStance, str, str]:
    present = [domain for domain in spec.consumed_domains if int(domain_states[domain].get("source_count") or 0) > 0]
    missing_required = [domain for domain in spec.required_domains if domain_states[domain].get("status") == "MISSING"]
    stale_required = [domain for domain in spec.required_domains if domain_states[domain].get("status") == "STALE"]
    stale_core = [domain for domain in stale_required if domain in {AwarenessDomain.ORDERBOOK, AwarenessDomain.LIQUIDITY}]
    summaries = " | ".join(str(domain_states[domain].get("summary") or "") for domain in spec.consumed_domains).upper()
    if not present:
        return BrainStance.NO_SIGNAL, "OBSERVE", f"{spec.brain_name} found no source-backed domains in shared awareness."
    if spec.brain_type == BrainType.RISK_BRAIN:
        if "NO_TRADE" in summaries or "COMPLIANCE_BLOCK" in summaries or "WORDING_RISK_HIGH" in summaries:
            return BrainStance.BLOCK, "PROTECT", "Risk Brain found source-backed rules or no-trade wording risk."
        if stale_core:
            return BrainStance.CAUTION, "PROTECT", "Risk Brain found stale liquidity/orderbook awareness."
        if len(missing_required) >= 3:
            return BrainStance.CAUTION, "PROTECT", "Risk Brain is missing several required domains."
        return BrainStance.SUPPORT, "ALLOW_REVIEW", "Risk Brain found no blocking risk in consumed shared awareness."
    if spec.brain_type == BrainType.EXIT_BRAIN:
        if "CLOSED" in summaries or "EXIT_REQUIRED" in summaries or "BLOCK" in summaries:
            return BrainStance.CAUTION, "PROTECT", "Exit Brain found adverse risk/exit context."
        if stale_core:
            return BrainStance.CAUTION, "PROTECT", "Exit Brain found stale exit-relevant liquidity/orderbook awareness."
        if missing_required and not session.get("position_id"):
            return BrainStance.NO_SIGNAL, "OBSERVE", "Exit Brain has no position-grade exit context yet."
        return BrainStance.SUPPORT, "OBSERVE", "Exit Brain found usable exit context for observation."
    if spec.brain_type == BrainType.CAPITAL_BRAIN:
        if capital_evaluation:
            decision = str(capital_evaluation.get("decision") or "")
            reason = str(capital_evaluation.get("reason") or "Capital Brain consumed upstream capital evaluation.")
            if decision == "CAPITAL_SUPPORT":
                return BrainStance.SUPPORT, "ALLOW_REVIEW", reason
            if decision == "CAPITAL_WATCH":
                return BrainStance.CAUTION, "PROTECT", reason
            if decision == "CAPITAL_BLOCK":
                return BrainStance.BLOCK, "PROTECT", reason
            if decision == "CAPITAL_RELEASE_REVIEW":
                return BrainStance.CAUTION, "PROTECT", reason
            return BrainStance.NO_SIGNAL, "OBSERVE", reason
        capital = domain_states[AwarenessDomain.CAPITAL]
        capital_summary = str(capital.get("summary") or "").upper()
        if capital.get("status") == "MISSING":
            return BrainStance.BLOCK, "PROTECT", "Capital Brain cannot reason without capital state."
        if "AVAILABLE=0" in capital_summary or "AVAILABLE=0.0" in capital_summary:
            return BrainStance.BLOCK, "PROTECT", "Capital Brain found no available paper capital."
        if "LOCKED" in capital_summary and "AVAILABLE=" in capital_summary:
            return BrainStance.SUPPORT, "ALLOW_REVIEW", "Capital Brain found source-backed capital state."
        return BrainStance.CAUTION, "PROTECT", "Capital Brain found partial capital context."
    if spec.brain_type == BrainType.CONTEXT_BRAIN:
        if not present:
            return BrainStance.NO_SIGNAL, "OBSERVE", "Context Brain found no context domains."
        if len(missing_required) == len(spec.required_domains) and len(present) <= 1:
            return BrainStance.NO_SIGNAL, "OBSERVE", "Context Brain has only optional or sparse context domains."
        if "RULES" in [domain.value for domain in present] or "NEWS" in [domain.value for domain in present] or "CANDIDATE" in [domain.value for domain in present]:
            return BrainStance.SUPPORT, "OBSERVE", "Context Brain consumed source-backed context domains."
        return BrainStance.NO_SIGNAL, "OBSERVE", "Context Brain found optional context only."
    if spec.brain_type == BrainType.POSITION_BRAIN:
        if not (_position_brain_applicable(session, domain_states) or position_awareness):
            return BrainStance.NO_SIGNAL, "OBSERVE", "Position Brain has no position context."
        if position_awareness:
            if _position_awareness_adverse(position_awareness):
                return BrainStance.CAUTION, "PROTECT", "Position Brain consumed living position awareness with adverse context."
            return BrainStance.SUPPORT, "OBSERVE", "Position Brain consumed living position awareness and found no adverse trigger."
        if "CLOSED" in summaries or "BLOCK" in summaries:
            return BrainStance.CAUTION, "PROTECT", "Position Brain found adverse position context."
        return BrainStance.SUPPORT, "OBSERVE", "Position Brain consumed source-backed position context."
    return BrainStance.NO_SIGNAL, "OBSERVE", "No deterministic opinion rule matched."


def _opinion_confidence(
    spec: BrainSpec,
    domain_states: dict[AwarenessDomain, dict[str, Any]],
    stance: BrainStance,
) -> float:
    states = [domain_states[domain] for domain in spec.consumed_domains if int(domain_states[domain].get("source_count") or 0) > 0]
    if not states:
        return 0.0
    average = sum(float(state.get("confidence") or 0) for state in states) / len(states)
    coverage = len(states) / len(spec.consumed_domains)
    penalty = 0.1 if stance == BrainStance.CAUTION else 0.2 if stance == BrainStance.BLOCK else 0.0
    return round(max(0.0, min(1.0, (average * 0.7) + (coverage * 0.3) - penalty)), 4)


def _position_awareness_adverse(position_awareness: dict[str, Any]) -> bool:
    text = " ".join(
        str(position_awareness.get(key) or "")
        for key in ("liquidity_status", "risk_status", "exit_status", "capital_status", "coordinator_status")
    ).upper()
    return any(
        token in text
        for token in (
            "DETERIORATED",
            "WORSENED",
            "DEGRADED",
            "BLOCK",
            "CAPITAL_PRESSURE",
            "CAPITAL_RELEASE_REVIEW",
            "EXIT_REVIEW",
            "CAUTION",
        )
    )


def _source_refs_for_domains(
    domain_states: dict[AwarenessDomain, dict[str, Any]],
    sources: list[dict[str, Any]],
    domains: tuple[AwarenessDomain, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    source_by_key = {
        (str(source["source_domain"]), str(source["source_table"]), str(source["source_record_id"])): source
        for source in sources
    }
    supporting: list[dict[str, Any]] = []
    opposing: list[dict[str, Any]] = []
    opinion_sources: list[dict[str, Any]] = []
    for domain in domains:
        state = domain_states[domain]
        status = str(state.get("status") or "MISSING")
        for ref in state.get("source_refs") or []:
            key = (domain.value, str(ref.get("source_table")), str(ref.get("source_record_id")))
            source = source_by_key.get(key, {})
            row = {
                "source_domain": domain.value,
                "source_table": str(ref.get("source_table")),
                "source_record_id": str(ref.get("source_record_id")),
                "source_status": status,
                "influence": "OPPOSING" if status == "STALE" else "SUPPORTING",
                "contribution_summary": str(ref.get("summary") or source.get("contribution_summary") or f"{domain.value} awareness source"),
            }
            opinion_sources.append(row)
            display_ref = {
                "source_domain": row["source_domain"],
                "source_table": row["source_table"],
                "source_record_id": row["source_record_id"],
                "source_status": row["source_status"],
                "summary": row["contribution_summary"],
            }
            if row["influence"] == "OPPOSING":
                opposing.append(display_ref)
            else:
                supporting.append(display_ref)
    return supporting[:20], opposing[:20], _dedupe_sources(opinion_sources)


def _detect_conflicts(opinions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    support = [opinion for opinion in opinions if opinion.get("stance") == BrainStance.SUPPORT.value]
    block = [opinion for opinion in opinions if opinion.get("stance") == BrainStance.BLOCK.value]
    conflicts: list[dict[str, Any]] = []
    if support and block:
        for left in support:
            for right in block:
                conflicts.append(
                    {
                        "conflict_type": "stance_disagreement",
                        "left_brain": left.get("brain_type"),
                        "left_stance": left.get("stance"),
                        "right_brain": right.get("brain_type"),
                        "right_stance": right.get("stance"),
                        "summary": f"{left.get('brain_name')} SUPPORT conflicts with {right.get('brain_name')} BLOCK.",
                    }
                )
    return conflicts


def _position_brain_applicable(session: dict[str, Any], domain_states: dict[AwarenessDomain, dict[str, Any]]) -> bool:
    if session.get("position_id") or session.get("session_type") == "POSITION_SESSION":
        return True
    return int(domain_states[AwarenessDomain.POSITION].get("source_count") or 0) > 0


def _domain_states(awareness: dict[str, Any]) -> dict[AwarenessDomain, dict[str, Any]]:
    return {domain: awareness.get(DOMAIN_STATE_COLUMNS[domain]) or {} for domain in ALL_DOMAINS}


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for source in sources:
        key = (source["source_domain"], source["source_table"], source["source_record_id"])
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _missing_domain_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {domain.value: 0 for domain in ALL_DOMAINS}
    for row in rows:
        for domain in row.get("missing_domains_json") or []:
            if domain in counts:
                counts[domain] += 1
    return counts


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
        "total_sessions_with_opinions": 0,
        "total_brain_opinions": 0,
        "avg_source_brain_count": 0.0,
        "sessions_with_source_brain_count_gt_1": 0,
        "conflicts_detected_count": 0,
        "brain_participation_by_type": {},
        "missing_domain_counts": {domain.value: 0 for domain in ALL_DOMAINS},
        "latest_bundles": [],
    }
