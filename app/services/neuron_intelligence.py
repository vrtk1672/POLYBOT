from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.system_power import SystemPowerService


SPREAD_TOO_WIDE = Decimal("0.08")
MIN_LIQUIDITY_SCORE = Decimal("0.25")


class NeuronIntelligenceService:
    """Pack 1 source-backed neuron evidence materialization."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)

    def run_pack(self, *, cycle_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"neuron_intelligence_{uuid4().hex}"
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        if system_power != "ON" or not bool(power.get("runtime_work_allowed")):
            payload = self._run_payload(run_id, cycle_id, system_power, started_at, "SYSTEM_POWER_OFF")
            self._record_run(payload)
            return _json_safe(payload)
        if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
            payload = self._run_payload(run_id, cycle_id, system_power, started_at, "BLOCKED", error_message="STATE_GOVERNOR_BLOCKED_INTELLIGENCE")
            self._record_run(payload)
            return _json_safe(payload)
        if not self._factory.enabled:
            return self._run_payload(run_id, cycle_id, system_power, started_at, "NO_CANDIDATES")

        errors: list[str] = []
        counts: Counter[str] = Counter()
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "neuron_intelligence_runs"):
                raise RuntimeError("neuron_intelligence schema is missing")
            candidates = _load_candidates(conn, limit=limit)
            if not candidates:
                payload = self._run_payload(run_id, cycle_id, system_power, started_at, "NO_CANDIDATES")
                self._insert_run(conn, payload)
                return _json_safe(payload)
            self._insert_run(
                conn,
                self._run_payload(run_id, cycle_id, system_power, started_at, "OK", candidates_checked=len(candidates)),
            )
            for candidate in candidates:
                try:
                    for evidence in (
                        self._rules_evidence(conn, run_id, cycle_id, candidate),
                        self._liquidity_evidence(run_id, cycle_id, candidate),
                        self._fees_evidence(conn, run_id, cycle_id, candidate),
                        self._time_evidence(conn, run_id, cycle_id, candidate),
                        self._news_evidence(conn, run_id, cycle_id, candidate),
                    ):
                        self._insert_evidence(conn, evidence)
                        counts[evidence["neuron_name"]] += 1
                        if evidence["status"] == "BLOCKED":
                            counts["blocked"] += 1
                except Exception as exc:
                    errors.append(f"{candidate.get('candidate_id') or candidate.get('market_id')}:{type(exc).__name__}:{exc}")
            status = "DEGRADED" if errors else "OK"
            payload = self._run_payload(
                run_id,
                cycle_id,
                system_power,
                started_at,
                status,
                candidates_checked=len(candidates),
                rules_evidence_count=counts["Rules / Wording Neuron"],
                liquidity_evidence_count=counts["Liquidity Neuron"],
                fees_evidence_count=counts["Fees / Rewards Neuron"],
                time_evidence_count=counts["Time Neuron"],
                news_evidence_count=counts["News Neuron"],
                blocked_count=counts["blocked"],
                error_message="; ".join(errors) if errors else None,
            )
            self._update_run(conn, payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "evidence": []}
        with self._factory.connect() as conn:
            latest = _latest_run(conn)
            evidence = _latest_evidence(conn, limit=limit)
            by_neuron = {}
            for name in ("Rules / Wording Neuron", "Liquidity Neuron", "Fees / Rewards Neuron", "Time Neuron", "News Neuron"):
                rows = _latest_evidence(conn, limit=1, neuron_name=name)
                by_neuron[name] = rows[0] if rows else None
            power = self._system_power.get_power_state()
        return _json_safe(
            {
                "mock_data": False,
                "status": (latest or {}).get("status") or "EMPTY",
                "system_power": power.get("power"),
                "runtime_work_allowed": power.get("runtime_work_allowed"),
                "latest_run": latest,
                "rules": _scores(by_neuron.get("Rules / Wording Neuron")),
                "liquidity": _scores(by_neuron.get("Liquidity Neuron")),
                "fees": _scores(by_neuron.get("Fees / Rewards Neuron")),
                "time": _scores(by_neuron.get("Time Neuron")),
                "news": _scores(by_neuron.get("News Neuron")),
                "recent_evidence": evidence,
                "last_updated": datetime.now(UTC).isoformat(),
            }
        )

    def _rules_evidence(self, conn: Any, run_id: str, cycle_id: str | None, candidate: dict[str, Any]) -> dict[str, Any]:
        rules = _latest_row(conn, "rules_analysis", "market_id", candidate["market_id"], "created_at")
        market_rules = _latest_row(conn, "market_rules", "market_id", candidate["market_id"], "updated_at")
        if rules:
            wording = _decimal(rules.get("wording_risk"))
            clarity = _decimal(rules.get("resolution_clarity"))
            ambiguity = _bounded(wording)
            subjectivity = _subjectivity_from_rules(market_rules)
            confidence = _bounded(clarity)
            decision = "HIGH_RESOLUTION_RISK" if wording >= Decimal("0.75") else "AMBIGUOUS" if wording >= Decimal("0.45") else "CLEAR" if clarity >= Decimal("0.65") else "LOW_CONFIDENCE"
            blockers = [] if decision in {"CLEAR"} else [decision]
            source_table = "rules_analysis"
            source_record_id = str(rules.get("rules_analysis_id") or rules.get("id"))
        else:
            wording = Decimal("0")
            clarity = Decimal("0")
            ambiguity = Decimal("0")
            subjectivity = _subjectivity_from_rules(market_rules)
            confidence = Decimal("0")
            decision = "LOW_CONFIDENCE"
            blockers = ["MISSING_RULES_ANALYSIS"]
            source_table = "market_rules" if market_rules else "paper_eligibility_candidates"
            source_record_id = str((market_rules or candidate).get("id") or candidate["candidate_id"])
        scores = {
            "wording_risk_score": wording,
            "resolution_clarity_score": clarity,
            "ambiguity_score": ambiguity,
            "subjectivity_score": subjectivity,
            "rules_confidence": confidence,
        }
        message = f"Rules / Wording Neuron: decision={decision}; wording_risk={float(wording):.3f}, resolution_clarity={float(clarity):.3f} for market={candidate['market_id']}."
        return _evidence(run_id, cycle_id, candidate, "Rules / Wording Neuron", source_table, source_record_id, decision, "OK" if not blockers else "BLOCKED", scores, blockers, message)

    def _liquidity_evidence(self, run_id: str, cycle_id: str | None, candidate: dict[str, Any]) -> dict[str, Any]:
        spread = _decimal(candidate.get("spread"))
        liquidity = _bounded(candidate.get("liquidity_score"), Decimal("0.5"))
        depth = _bounded(liquidity)
        spread_penalty = _bounded(spread / SPREAD_TOO_WIDE if SPREAD_TOO_WIDE else Decimal("0"))
        entry = _bounded(liquidity * (Decimal("1") - spread_penalty / Decimal("2")))
        exit_score = _bounded((liquidity * Decimal("0.7")) + ((Decimal("1") - spread_penalty) * Decimal("0.3")))
        expected_slippage = max(Decimal("0"), spread / Decimal("2"))
        if spread > SPREAD_TOO_WIDE:
            decision = "SPREAD_TOO_WIDE"
        elif liquidity < MIN_LIQUIDITY_SCORE:
            decision = "LOW_DEPTH"
        elif exit_score < Decimal("0.35"):
            decision = "EXIT_RISK"
        else:
            decision = "GOOD_LIQUIDITY"
        blockers = [] if decision == "GOOD_LIQUIDITY" else [decision]
        scores = {
            "entry_liquidity_score": entry,
            "exit_liquidity_score": exit_score,
            "expected_slippage": expected_slippage,
            "depth_score": depth,
            "liquidity_confidence": liquidity,
        }
        message = f"Liquidity Neuron: decision={decision}; spread={float(spread):.4f}, exit_liquidity={float(exit_score):.3f} for market={candidate['market_id']}."
        return _evidence(run_id, cycle_id, candidate, "Liquidity Neuron", "orderbook_snapshots", candidate.get("orderbook_snapshot_id"), decision, "OK" if not blockers else "BLOCKED", scores, blockers, message)

    def _fees_evidence(self, conn: Any, run_id: str, cycle_id: str | None, candidate: dict[str, Any]) -> dict[str, Any]:
        fee = _latest_row(conn, "fee_snapshots", "market_id", candidate["market_id"], "snapshot_at")
        spread = _decimal(candidate.get("spread"))
        maker = _bps((fee or {}).get("maker_fee") or (fee or {}).get("maker_cost_bps"))
        taker = _bps((fee or {}).get("taker_fee") or (fee or {}).get("taker_cost_bps"))
        spread_cost = spread * Decimal("10000")
        estimated_cost = (maker + taker + spread_cost) / Decimal("10000")
        expected_edge = _decimal(candidate.get("expected_edge"), Decimal("0"))
        net_edge = expected_edge - estimated_cost
        penalty = _bounded(estimated_cost * Decimal("10"))
        decision = "PROFITABLE_AFTER_COSTS" if net_edge > 0 else "EDGE_ERASED_BY_COSTS"
        scores = {
            "estimated_fees": (maker + taker) / Decimal("10000"),
            "estimated_cost": estimated_cost,
            "net_edge_after_costs": net_edge,
            "fee_penalty_score": penalty,
        }
        message = f"Fees / Rewards Neuron: decision={decision}; estimated_cost={float(estimated_cost):.4f}, net_edge_after_costs={float(net_edge):.4f} for market={candidate['market_id']}."
        return _evidence(run_id, cycle_id, candidate, "Fees / Rewards Neuron", "fee_snapshots" if fee else "orderbook_snapshots", (fee or {}).get("id") or candidate.get("orderbook_snapshot_id"), decision, "OK", scores, [] if decision == "PROFITABLE_AFTER_COSTS" else [decision], message)

    def _time_evidence(self, conn: Any, run_id: str, cycle_id: str | None, candidate: dict[str, Any]) -> dict[str, Any]:
        market = _latest_market(conn, candidate["market_id"])
        close_time = _dt((market or {}).get("end_date") or (market or {}).get("market_close_time") or (market or {}).get("close_time"))
        seconds = None if close_time is None else max(0, int((close_time - datetime.now(UTC)).total_seconds()))
        if seconds is None:
            efficiency = Decimal("0")
            opportunity = Decimal("1")
            decision = "POOR_TIME_EFFICIENCY"
            blockers = ["MISSING_MARKET_CLOSE_TIME"]
        else:
            hours = Decimal(seconds) / Decimal("3600")
            lock = _bounded(Decimal(seconds) / Decimal(30 * 86400))
            urgency = _bounded(Decimal("1") - Decimal(seconds) / Decimal("86400"))
            efficiency = _bounded((urgency * Decimal("0.45")) + ((Decimal("1") - lock) * Decimal("0.55")))
            opportunity = lock
            decision = "FAST_RESOLUTION" if seconds <= 6 * 3600 else "LONG_CAPITAL_LOCK" if seconds >= 7 * 86400 else "POOR_TIME_EFFICIENCY" if efficiency < Decimal("0.35") else "FAST_RESOLUTION"
            blockers = [] if decision == "FAST_RESOLUTION" else [decision]
        scores = {
            "time_to_resolution": seconds,
            "capital_lock_duration": seconds,
            "time_efficiency_score": efficiency,
            "opportunity_cost_score": opportunity,
        }
        message = f"Time Neuron: decision={decision}; time_to_resolution={seconds} seconds for market={candidate['market_id']}."
        return _evidence(run_id, cycle_id, candidate, "Time Neuron", "markets_v2", (market or {}).get("id") or candidate["market_id"], decision, "OK" if not blockers else "BLOCKED", scores, blockers, message)

    def _news_evidence(self, conn: Any, run_id: str, cycle_id: str | None, candidate: dict[str, Any]) -> dict[str, Any]:
        impact = _latest_row(conn, "news_impact_scores", "market_id", candidate["market_id"], "created_at")
        if not impact:
            scores = {
                "news_impact_score": Decimal("0"),
                "news_confidence": Decimal("0"),
                "news_relevance": Decimal("0"),
                "source_reliability": Decimal("0"),
            }
            message = f"News Neuron: no source-backed news impact evidence found for market={candidate['market_id']}; I remain UNVERIFIED."
            return _evidence(run_id, cycle_id, candidate, "News Neuron", "news_impact_scores", candidate["candidate_id"], "UNVERIFIED", "BLOCKED", scores, ["NO_NEWS_EVIDENCE"], message)
        impact_score = _bounded(impact.get("strength"))
        confidence = _bounded(impact.get("confidence"))
        relevance = _bounded(impact_score * confidence)
        reliability = _bounded(impact.get("source_reliability"), Decimal("0.5"))
        decision = "MARKET_MOVING" if impact_score >= Decimal("0.75") and confidence >= Decimal("0.7") else "HIGH_RELEVANCE" if relevance >= Decimal("0.45") else "LOW_RELEVANCE"
        scores = {
            "news_impact_score": impact_score,
            "news_confidence": confidence,
            "news_relevance": relevance,
            "source_reliability": reliability,
        }
        message = f"News Neuron: decision={decision}; news_impact={float(impact_score):.3f}, confidence={float(confidence):.3f} for market={candidate['market_id']}."
        return _evidence(run_id, cycle_id, candidate, "News Neuron", "news_impact_scores", impact.get("impact_id") or impact.get("id"), decision, "OK", scores, [], message)

    def _insert_evidence(self, conn: Any, item: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO neuron_intelligence_evidence (
                evidence_id, run_id, cycle_id, candidate_id, market_id, side,
                neuron_name, source_table, source_record_id, decision, status,
                score, confidence, scores_json, evidence_json, consumed_by_json,
                blockers_json, human_message, created_at
            )
            VALUES (
                %(evidence_id)s, %(run_id)s, %(cycle_id)s, %(candidate_id)s,
                %(market_id)s, %(side)s, %(neuron_name)s, %(source_table)s,
                %(source_record_id)s, %(decision)s, %(status)s, %(score)s,
                %(confidence)s, %(scores_json)s, %(evidence_json)s,
                %(consumed_by_json)s, %(blockers_json)s, %(human_message)s, now()
            )
            ON CONFLICT (evidence_id) DO NOTHING
            """,
            {
                **item,
                "scores_json": Jsonb(_json_safe(item.get("scores_json") or {})),
                "evidence_json": Jsonb(_json_safe(item.get("evidence_json") or {})),
                "consumed_by_json": Jsonb(item.get("consumed_by_json") or []),
                "blockers_json": Jsonb(item.get("blockers_json") or []),
            },
        )

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if _table_exists(conn, "neuron_intelligence_runs"):
                self._insert_run(conn, payload)

    def _insert_run(self, conn: Any, payload: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO neuron_intelligence_runs (
                run_id, cycle_id, system_power, started_at, finished_at, status,
                candidates_checked, rules_evidence_count, liquidity_evidence_count,
                fees_evidence_count, time_evidence_count, news_evidence_count,
                blocked_count, error_message, metadata_json, created_at
            )
            VALUES (
                %(run_id)s, %(cycle_id)s, %(system_power)s, %(started_at)s,
                %(finished_at)s, %(status)s, %(candidates_checked)s,
                %(rules_evidence_count)s, %(liquidity_evidence_count)s,
                %(fees_evidence_count)s, %(time_evidence_count)s,
                %(news_evidence_count)s, %(blocked_count)s, %(error_message)s,
                %(metadata_json)s, now()
            )
            ON CONFLICT (run_id) DO NOTHING
            """,
            {**payload, "metadata_json": Jsonb(_json_safe(payload.get("metadata_json") or {}))},
        )

    def _update_run(self, conn: Any, payload: dict[str, Any]) -> None:
        conn.execute(
            """
            UPDATE neuron_intelligence_runs
            SET finished_at=%(finished_at)s,
                status=%(status)s,
                candidates_checked=%(candidates_checked)s,
                rules_evidence_count=%(rules_evidence_count)s,
                liquidity_evidence_count=%(liquidity_evidence_count)s,
                fees_evidence_count=%(fees_evidence_count)s,
                time_evidence_count=%(time_evidence_count)s,
                news_evidence_count=%(news_evidence_count)s,
                blocked_count=%(blocked_count)s,
                error_message=%(error_message)s,
                metadata_json=%(metadata_json)s
            WHERE run_id=%(run_id)s
            """,
            {**payload, "metadata_json": Jsonb(_json_safe(payload.get("metadata_json") or {}))},
        )

    def _run_payload(
        self,
        run_id: str,
        cycle_id: str | None,
        system_power: str,
        started_at: datetime,
        status: str,
        *,
        candidates_checked: int = 0,
        rules_evidence_count: int = 0,
        liquidity_evidence_count: int = 0,
        fees_evidence_count: int = 0,
        time_evidence_count: int = 0,
        news_evidence_count: int = 0,
        blocked_count: int = 0,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": status,
            "candidates_checked": candidates_checked,
            "rules_evidence_count": rules_evidence_count,
            "liquidity_evidence_count": liquidity_evidence_count,
            "fees_evidence_count": fees_evidence_count,
            "time_evidence_count": time_evidence_count,
            "news_evidence_count": news_evidence_count,
            "blocked_count": blocked_count,
            "error_message": error_message,
            "metadata_json": {"non_trading_evidence_only": True},
        }


def _load_candidates(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "trusted_orderbook_evidence_links"):
        return []
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                tol.candidate_id,
                tol.market_id,
                tol.side,
                tol.expected_token_id,
                tol.orderbook_snapshot_id,
                tol.best_bid,
                tol.best_ask,
                tol.mid_price,
                tol.spread,
                tol.evidence_json,
                pec.evidence->>'expected_edge' AS expected_edge,
                obs.liquidity_score,
                obs.token_id,
                obs.created_at AS orderbook_created_at
            FROM trusted_orderbook_evidence_links tol
            LEFT JOIN paper_eligibility_candidates pec ON pec.eligibility_id = tol.candidate_id
            LEFT JOIN orderbook_snapshots obs ON obs.id = tol.orderbook_snapshot_id
            WHERE tol.trusted IS true
            ORDER BY tol.created_at DESC, tol.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    ]


def _evidence(
    run_id: str,
    cycle_id: str | None,
    candidate: dict[str, Any],
    neuron_name: str,
    source_table: str,
    source_record_id: Any,
    decision: str,
    status: str,
    scores: dict[str, Any],
    blockers: list[str],
    human_message: str,
) -> dict[str, Any]:
    score_values = [_decimal(value) for value in scores.values() if isinstance(value, (int, float, Decimal, str))]
    score = sum(score_values) / Decimal(len(score_values)) if score_values else None
    confidence = scores.get("rules_confidence") or scores.get("liquidity_confidence") or scores.get("news_confidence") or scores.get("time_efficiency_score") or Decimal("0.5")
    return {
        "evidence_id": f"neuron_intel_{uuid4().hex}",
        "run_id": run_id,
        "cycle_id": cycle_id,
        "candidate_id": candidate.get("candidate_id"),
        "market_id": str(candidate["market_id"]),
        "side": candidate.get("side"),
        "neuron_name": neuron_name,
        "source_table": source_table,
        "source_record_id": str(source_record_id) if source_record_id is not None else None,
        "decision": decision,
        "status": status,
        "score": score,
        "confidence": _decimal(confidence),
        "scores_json": scores,
        "evidence_json": {
            "trusted_orderbook_snapshot_id": candidate.get("orderbook_snapshot_id"),
            "token_id": candidate.get("token_id") or candidate.get("expected_token_id"),
            "side": candidate.get("side"),
            "source_table": source_table,
            "source_record_id": str(source_record_id) if source_record_id is not None else None,
        },
        "consumed_by_json": ["Risk Gate", "Exit Cortex", "Eligibility Gate", "Opportunity Score"],
        "blockers_json": blockers,
        "human_message": human_message,
    }


def _latest_row(conn: Any, table: str, where_col: str, where_value: Any, order_col: str) -> dict[str, Any] | None:
    if not _table_exists(conn, table) or where_value is None:
        return None
    row = conn.execute(
        f"SELECT * FROM {table} WHERE {where_col} = %s ORDER BY {order_col} DESC NULLS LAST, id DESC LIMIT 1",
        (where_value,),
    ).fetchone()
    return dict(row) if row else None


def _latest_market(conn: Any, market_id: str) -> dict[str, Any] | None:
    for table, col, order_col in (
        ("markets_v2", "market_id", "updated_at"),
        ("market_snapshots_v2", "market_id", "snapshot_at"),
        ("market_snapshots", "market_id", "created_at"),
    ):
        row = _latest_row(conn, table, col, market_id, order_col)
        if row:
            return row
    return None


def _latest_run(conn: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, "neuron_intelligence_runs"):
        return None
    row = conn.execute("SELECT * FROM neuron_intelligence_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
    return _json_safe(dict(row)) if row else None


def _latest_evidence(conn: Any, *, limit: int, neuron_name: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "neuron_intelligence_evidence"):
        return []
    params: list[Any] = []
    where = ""
    if neuron_name:
        where = "WHERE neuron_name = %s"
        params.append(neuron_name)
    params.append(limit)
    return [
        _json_safe(dict(row))
        for row in conn.execute(
            f"SELECT * FROM neuron_intelligence_evidence {where} ORDER BY created_at DESC, id DESC LIMIT %s",
            tuple(params),
        ).fetchall()
    ]


def _scores(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return dict(row.get("scores_json") or {})


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _subjectivity_from_rules(row: dict[str, Any] | None) -> Decimal:
    text = str((row or {}).get("rules_text") or "").lower()
    if not text:
        return Decimal("0")
    terms = ("reasonable", "substantial", "significant", "material", "likely", "best effort", "may", "should")
    hits = sum(1 for term in terms if term in text)
    return _bounded(Decimal(hits) / Decimal("4"))


def _bps(value: Any) -> Decimal:
    number = _decimal(value)
    if Decimal("0") < number < Decimal("1"):
        return number * Decimal("10000")
    return number


def _bounded(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    number = _decimal(value, default)
    return max(Decimal("0"), min(Decimal("1"), number))


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
