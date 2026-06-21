from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.truth_state import TruthStateService


SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"

DEFAULT_TTLS = {
    "MARKET_IDENTITY": 600,
    "TOKEN_IDENTITY": 600,
    "ORDERBOOK_SNAPSHOT": 180,
    "TRUSTED_ORDERBOOK": 180,
    "EXECUTABLE_PRICE": 180,
    "RISK_DECISION": 600,
    "EXIT_PLAN": 600,
    "CAPITAL_EVALUATION": 600,
    "PAYOUT_ODDS": 600,
    "EXIT_HOLD": 600,
    "CAPITAL_EFFICIENCY": 600,
    "LIFECYCLE_PLAN": 600,
    "LIFECYCLE_GOVERNANCE": 600,
    "SAME_MARKET_GUARD": 600,
    "PAPER_INTENT": 600,
    "PAPER_CANDIDATE": 600,
    "MESH_COORDINATOR": 600,
}

CRITICAL_SOURCE_TYPES = {
    "MARKET_IDENTITY",
    "TOKEN_IDENTITY",
    "ORDERBOOK_SNAPSHOT",
    "TRUSTED_ORDERBOOK",
    "EXECUTABLE_PRICE",
    "RISK_DECISION",
    "EXIT_PLAN",
    "CAPITAL_EVALUATION",
    "LIFECYCLE_PLAN",
    "LIFECYCLE_GOVERNANCE",
    "SAME_MARKET_GUARD",
    "PAPER_INTENT",
    "PAPER_CANDIDATE",
}

STALE_BLOCKERS = {
    "ORDERBOOK_SNAPSHOT": "STALE_ORDERBOOK",
    "TRUSTED_ORDERBOOK": "STALE_ORDERBOOK",
    "EXECUTABLE_PRICE": "STALE_ORDERBOOK",
    "RISK_DECISION": "STALE_RISK_DECISION",
    "EXIT_PLAN": "STALE_EXIT_PLAN",
    "CAPITAL_EVALUATION": "STALE_CAPITAL_EVALUATION",
    "LIFECYCLE_PLAN": "STALE_LIFECYCLE_PLAN",
    "LIFECYCLE_GOVERNANCE": "STALE_GOVERNANCE_DECISION",
    "SAME_MARKET_GUARD": "STALE_SAME_MARKET_GUARD",
    "PAPER_INTENT": "STALE_PAPER_INTENT",
    "PAPER_CANDIDATE": "STALE_PAPER_CANDIDATE",
}


class FreshnessGovernanceService:
    """Derived freshness truth for decision governance.

    Fresh checks are audit/governance records only. They never create paper
    intents, orders, fills, positions, closes, or capital ledger rows.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._truth = TruthStateService(connection_factory=self._factory)

    def evaluate_recent(self, *, limit: int = 100, dry_run: bool = False) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return _empty("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "trade_lifecycle_plans"):
                return _empty("MISSING_LIFECYCLE_TABLE", generated_at)
            before = _count_table(conn, "freshness_governance_checks")
            plans = _fetchall(
                conn,
                """
                SELECT *
                FROM trade_lifecycle_plans
                ORDER BY created_at DESC,id DESC
                LIMIT %s
                """,
                (limit,),
            )
            outcomes = [self.evaluate_plan_with_conn(conn, plan, request_action="OBSERVE", write_checks=not dry_run) for plan in plans]
            after = _count_table(conn, "freshness_governance_checks")
        statuses = Counter()
        blockers = Counter()
        for item in outcomes:
            for check in item.get("checks", []):
                statuses[str(check.get("freshness_status"))] += 1
            blockers.update(item.get("critical_blockers", []))
        return _json_safe(
            {
                "mock_data": False,
                "status": "DRY_RUN" if dry_run else "OK",
                "generated_at": generated_at,
                "plans_checked": len(plans),
                "checks_created": 0 if dry_run else max(0, after - before),
                "freshness_status_counts": dict(statuses),
                "critical_blockers": dict(blockers),
                "latest_outcomes": outcomes[:20],
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
            }
        )

    def evaluate_plan_with_conn(
        self,
        conn: Any,
        plan: dict[str, Any],
        *,
        request_action: str = "OBSERVE",
        metadata: dict[str, Any] | None = None,
        write_checks: bool = False,
    ) -> dict[str, Any]:
        subject_type = str(plan.get("subject_type") or "UNKNOWN")
        subject_id = str(plan.get("subject_id") or "")
        checks: list[dict[str, Any]] = []
        checks.append(self._check_record(
            conn,
            subject_type=subject_type,
            subject_id=subject_id,
            source_type="LIFECYCLE_PLAN",
            source_id=str(plan.get("plan_id") or ""),
            timestamp=plan.get("updated_at") or plan.get("created_at"),
            request_action=request_action,
        ))
        refs = _dict(plan.get("source_refs_json"))
        for spec in _source_specs(refs):
            check = self._check_source(conn, subject_type=subject_type, subject_id=subject_id, request_action=request_action, **spec)
            if check:
                checks.append(check)
        if subject_type == "PAPER_INTENT":
            intent = _fetchone(conn, "SELECT created_at,updated_at FROM paper_intents WHERE paper_intent_id=%s", (subject_id,)) if _table_exists(conn, "paper_intents") else None
            if intent:
                checks.append(self._check_record(
                    conn,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    source_type="PAPER_INTENT",
                    source_id=subject_id,
                    timestamp=intent.get("updated_at") or intent.get("created_at"),
                    request_action=request_action,
                ))
        if subject_type == "PAPER_CANDIDATE":
            candidate = _fetchone(conn, "SELECT updated_at,created_at FROM paper_eligibility_candidates WHERE eligibility_id=%s", (subject_id,)) if _table_exists(conn, "paper_eligibility_candidates") else None
            if candidate:
                checks.append(self._check_record(
                    conn,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    source_type="PAPER_CANDIDATE",
                    source_id=subject_id,
                    timestamp=candidate.get("updated_at") or candidate.get("created_at"),
                    request_action=request_action,
                ))
        critical = []
        for check in checks:
            if check["decision_impact"] == "CRITICAL_BLOCKER" and check["freshness_status"] in {"STALE", "EXPIRED", "REFRESH_REQUIRED", "UNKNOWN_FRESHNESS"}:
                blocker = STALE_BLOCKERS.get(check["source_type"], f"STALE_{check['source_type']}")
                critical.append(blocker)
        if critical and request_action == "PAPER_EXECUTION":
            critical.append("REFRESH_REQUIRED_BEFORE_EXECUTION")
        if write_checks and _table_exists(conn, "freshness_governance_checks"):
            for check in checks:
                _insert_check(conn, check)
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "subject_type": subject_type,
                "subject_id": subject_id,
                "request_action": request_action,
                "checks": checks,
                "critical_blockers": sorted(set(critical)),
                "stale_sources_count": len([c for c in checks if c["freshness_status"] in {"STALE", "EXPIRED", "REFRESH_REQUIRED", "UNKNOWN_FRESHNESS"}]),
                "metadata": metadata or {},
            }
        )

    def dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return _empty("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn:
            if not _table_exists(conn, "freshness_governance_checks"):
                return _empty("MISSING_TABLES", generated_at)
            status_counts = _fetchall(conn, "SELECT freshness_status, COUNT(*) AS count FROM freshness_governance_checks GROUP BY freshness_status ORDER BY count DESC")
            stale_sources = _fetchall(
                conn,
                """
                SELECT source_type, COUNT(*) AS count
                FROM freshness_governance_checks
                WHERE freshness_status IN ('STALE','EXPIRED','REFRESH_REQUIRED','UNKNOWN_FRESHNESS')
                GROUP BY source_type
                ORDER BY count DESC, source_type
                LIMIT %s
                """,
                (limit,),
            )
            latest = _fetchall(conn, "SELECT * FROM freshness_governance_checks ORDER BY created_at DESC,id DESC LIMIT %s", (limit,))
            old_intents = _old_intents_requiring_refresh(conn)
            stale_lifecycle = _stale_count(conn, "trade_lifecycle_plans", "updated_at", DEFAULT_TTLS["LIFECYCLE_PLAN"])
            stale_governance = _stale_count(conn, "lifecycle_governance_decisions", "created_at", DEFAULT_TTLS["LIFECYCLE_GOVERNANCE"])
            stale_risk = _stale_count(conn, "risk_decisions", "updated_at", DEFAULT_TTLS["RISK_DECISION"])
            stale_exit = _stale_count(conn, "exit_plans", "updated_at", DEFAULT_TTLS["EXIT_PLAN"])
        stale_total = sum(_int(row.get("count")) for row in stale_sources)
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "freshness_status_counts": {str(row["freshness_status"]): _int(row["count"]) for row in status_counts},
                "stale_sources_count": stale_total,
                "stale_sources_by_type": stale_sources,
                "old_intents_requiring_refresh": old_intents,
                "stale_lifecycle_plans": stale_lifecycle,
                "stale_governance_decisions": stale_governance,
                "stale_risk_decisions": stale_risk,
                "stale_exit_plans": stale_exit,
                "latest_checks": latest,
            }
        )

    def calibration_summary(self, *, limit: int = 50) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return _empty("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn:
            if not _table_exists(conn, "lifecycle_governance_decisions"):
                return _empty("MISSING_GOVERNANCE_TABLE", generated_at)
            actionability = _fetchall(conn, "SELECT actionability_class, COUNT(*) AS count FROM lifecycle_governance_decisions GROUP BY actionability_class ORDER BY count DESC")
            critical = _top_jsonb_values(conn, "critical_blockers_json", limit=limit)
            optional = _top_jsonb_values(conn, "optional_missing_json", limit=limit)
            optional_only = _fetchone(
                conn,
                """
                SELECT COUNT(*) AS count
                FROM lifecycle_governance_decisions
                WHERE jsonb_array_length(critical_blockers_json)=0
                  AND jsonb_array_length(optional_missing_json)>0
                  AND actionability_class='HARD_BLOCK'
                """,
            )
            closest = _fetchall(
                conn,
                """
                SELECT decision_id,subject_type,subject_id,market_id,side,actionability_class,
                       critical_blockers_json,optional_missing_json,context_dependent_missing_json,reason,created_at
                FROM lifecycle_governance_decisions
                WHERE actionability_class='WATCH_FOR_CONFIRMATION'
                ORDER BY jsonb_array_length(context_dependent_missing_json), created_at DESC,id DESC
                LIMIT %s
                """,
                (limit,),
            )
            stale = self.dashboard_summary(limit=limit)
        valid_critical = sum(_int(row.get("count")) for row in critical)
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "actionability_distribution": {str(row["actionability_class"]): _int(row["count"]) for row in actionability},
                "valid_critical_blockers": valid_critical,
                "critical_blockers_top": critical,
                "optional_missing_top": optional,
                "optional_misclassified_count": _int((optional_only or {}).get("count")),
                "overblocking_count": _int((optional_only or {}).get("count")),
                "closest_to_actionable": closest,
                "closest_to_actionable_count": len(closest),
                "stale_sources_count": stale.get("stale_sources_count", 0),
                "old_intents_requiring_refresh": stale.get("old_intents_requiring_refresh", 0),
                "stale_governance_decisions": stale.get("stale_governance_decisions", 0),
                "stale_lifecycle_plans": stale.get("stale_lifecycle_plans", 0),
                "stale_risk_decisions": stale.get("stale_risk_decisions", 0),
                "stale_exit_plans": stale.get("stale_exit_plans", 0),
            }
        )

    def _check_source(
        self,
        conn: Any,
        *,
        subject_type: str,
        subject_id: str,
        source_type: str,
        source_id: str | None,
        table: str,
        lookup_column: str,
        timestamp_column: str,
        request_action: str,
        alternate_lookup: str | None = None,
    ) -> dict[str, Any] | None:
        if not source_id:
            return None
        if not _table_exists(conn, table):
            return self._check_record(
                conn,
                subject_type=subject_type,
                subject_id=subject_id,
                source_type=source_type,
                source_id=source_id,
                timestamp=None,
                request_action=request_action,
                reason=f"{table} is unavailable",
            )
        row = _fetchone(conn, f"SELECT {timestamp_column} AS source_at FROM {table} WHERE {lookup_column}=%s ORDER BY {timestamp_column} DESC NULLS LAST,id DESC LIMIT 1", (source_id,))
        if not row and alternate_lookup:
            row = _fetchone(conn, f"SELECT {timestamp_column} AS source_at FROM {table} WHERE {alternate_lookup}=%s ORDER BY {timestamp_column} DESC NULLS LAST,id DESC LIMIT 1", (source_id,))
        return self._check_record(
            conn,
            subject_type=subject_type,
            subject_id=subject_id,
            source_type=source_type,
            source_id=source_id,
            timestamp=(row or {}).get("source_at"),
            request_action=request_action,
            reason=f"{source_type} source {source_id} freshness evaluated",
        )

    def _check_record(
        self,
        conn: Any,
        *,
        subject_type: str,
        subject_id: str,
        source_type: str,
        source_id: str | None,
        timestamp: Any,
        request_action: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        ttl = DEFAULT_TTLS.get(source_type)
        impact = "CRITICAL_BLOCKER" if source_type in CRITICAL_SOURCE_TYPES else "INFORMATIONAL"
        truth = self._truth.classify_source(source_type=source_type, created_at_source=timestamp, updated_at_source=timestamp)
        age = truth.get("age_seconds")
        status = _freshness_status_from_truth(str(truth.get("truth_state") or "UNKNOWN"), str(truth.get("decision_permission") or "UNKNOWN_PERMISSION"))
        if request_action in {"PAPER_INTENT", "PAPER_EXECUTION"} and impact == "CRITICAL_BLOCKER" and status != "FRESH":
            status = "REFRESH_REQUIRED"
        return {
            "check_id": _check_id(subject_type, subject_id, source_type, source_id, status),
            "subject_type": subject_type,
            "subject_id": subject_id,
            "source_type": source_type,
            "source_id": source_id,
            "freshness_status": status,
            "age_seconds": age,
            "ttl_seconds": ttl,
            "decision_impact": impact,
            "reason": reason or str(truth.get("freshness_reason") or f"{source_type} freshness is {status}"),
        }


def _source_specs(refs: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"source_type": "ORDERBOOK_SNAPSHOT", "source_id": refs.get("orderbook_snapshot_id"), "table": "orderbook_snapshots", "lookup_column": "orderbook_snapshot_id", "alternate_lookup": "id::text", "timestamp_column": "COALESCE(snapshot_at,collected_at,created_at)"},
        {"source_type": "RISK_DECISION", "source_id": refs.get("risk_decision_id"), "table": "risk_decisions", "lookup_column": "risk_decision_id", "timestamp_column": "updated_at"},
        {"source_type": "EXIT_PLAN", "source_id": refs.get("exit_plan_id"), "table": "exit_plans", "lookup_column": "exit_plan_id", "timestamp_column": "updated_at"},
        {"source_type": "PAYOUT_ODDS", "source_id": refs.get("payout_odds_evaluation_id"), "table": "payout_odds_evaluations", "lookup_column": "evaluation_id", "timestamp_column": "created_at"},
        {"source_type": "EXIT_HOLD", "source_id": refs.get("exit_hold_evaluation_id"), "table": "exit_hold_evaluations", "lookup_column": "evaluation_id", "timestamp_column": "created_at"},
        {"source_type": "CAPITAL_EFFICIENCY", "source_id": refs.get("capital_efficiency_evaluation_id"), "table": "capital_efficiency_evaluations", "lookup_column": "evaluation_id", "timestamp_column": "created_at"},
        {"source_type": "CAPITAL_EVALUATION", "source_id": refs.get("capital_brain_evaluation_id"), "table": "capital_brain_evaluations", "lookup_column": "evaluation_id", "timestamp_column": "created_at"},
        {"source_type": "SAME_MARKET_GUARD", "source_id": refs.get("same_market_guard_decision_id"), "table": "same_market_side_guard_decisions", "lookup_column": "decision_id", "timestamp_column": "created_at"},
        {"source_type": "MESH_COORDINATOR", "source_id": refs.get("mesh_coordinator_decision_id"), "table": "mesh_coordinator_decisions", "lookup_column": "decision_id", "timestamp_column": "created_at"},
    ]


def _insert_check(conn: Any, check: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO freshness_governance_checks (
            check_id,subject_type,subject_id,source_type,source_id,freshness_status,
            age_seconds,ttl_seconds,decision_impact,reason
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (check_id) DO UPDATE SET
            freshness_status=EXCLUDED.freshness_status,
            age_seconds=EXCLUDED.age_seconds,
            ttl_seconds=EXCLUDED.ttl_seconds,
            decision_impact=EXCLUDED.decision_impact,
            reason=EXCLUDED.reason,
            created_at=now()
        """,
        (
            check["check_id"],
            check["subject_type"],
            check["subject_id"],
            check["source_type"],
            check.get("source_id"),
            check["freshness_status"],
            check.get("age_seconds"),
            check.get("ttl_seconds"),
            check["decision_impact"],
            check["reason"],
        ),
    )


def _old_intents_requiring_refresh(conn: Any) -> int:
    if not _table_exists(conn, "paper_intents"):
        return 0
    row = _fetchone(
        conn,
        """
        SELECT COUNT(*) AS count
        FROM paper_intents
        WHERE intent_status IN ('CREATED','READY','EXECUTING')
          AND intent_type='PAPER_ENTRY_INTENT'
          AND paper_only=true
          AND live=false
          AND COALESCE(is_dry_run_generated,false)=false
          AND COALESCE(updated_at,created_at) < now() - (%s * interval '1 second')
        """,
        (DEFAULT_TTLS["PAPER_INTENT"],),
    )
    return _int((row or {}).get("count"))


def _stale_count(conn: Any, table: str, timestamp_column: str, ttl_seconds: int) -> int:
    if not _table_exists(conn, table):
        return 0
    row = _fetchone(conn, f"SELECT COUNT(*) AS count FROM {table} WHERE COALESCE({timestamp_column},created_at) < now() - (%s * interval '1 second')", (ttl_seconds,))
    return _int((row or {}).get("count"))


def _top_jsonb_values(conn: Any, column: str, *, limit: int) -> list[dict[str, Any]]:
    return _fetchall(
        conn,
        f"""
        SELECT value AS item, COUNT(*) AS count
        FROM lifecycle_governance_decisions, jsonb_array_elements_text({column}) AS value
        GROUP BY value
        ORDER BY count DESC, item
        LIMIT %s
        """,
        (limit,),
    )


def _check_id(subject_type: str, subject_id: str, source_type: str, source_id: str | None, status: str) -> str:
    raw = "|".join([subject_type, subject_id, source_type, str(source_id or ""), status])
    return f"freshness_check_{uuid5(NAMESPACE_URL, raw).hex}"


def _age_seconds(timestamp: Any) -> int | None:
    if timestamp is None:
        return None
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(timestamp, datetime):
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - timestamp.astimezone(UTC)).total_seconds()))


def _freshness_status_from_truth(truth_state: str, permission: str) -> str:
    if truth_state == "ACTIVE_FRESH" and permission == "CAN_AUTHORIZE":
        return "FRESH"
    if truth_state == "ACTIVE_FRESH":
        return "FRESH"
    if truth_state == "LAST_KNOWN":
        return "STALE"
    if truth_state == "HISTORICAL_ONLY":
        return "HISTORICAL_ONLY"
    if truth_state == "REFRESH_REQUIRED" or permission == "MUST_REFRESH":
        return "REFRESH_REQUIRED"
    if truth_state == "EXPIRED":
        return "EXPIRED"
    return "UNKNOWN_FRESHNESS"


def _empty(status: str, generated_at: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "generated_at": generated_at,
        "security_governance_status": SECURITY_GOVERNANCE_STATUS,
        "stale_sources_count": 0,
        "old_intents_requiring_refresh": 0,
        "stale_governance_decisions": 0,
        "stale_lifecycle_plans": 0,
        "stale_risk_decisions": 0,
        "stale_exit_plans": 0,
        "latest_checks": [],
    }


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
