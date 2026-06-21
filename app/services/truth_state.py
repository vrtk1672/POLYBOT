from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory


SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"

TRUTH_STATES = {
    "ACTIVE_FRESH",
    "LAST_KNOWN",
    "HISTORICAL_ONLY",
    "EXPIRED",
    "UNKNOWN",
    "REFRESH_REQUIRED",
}

DECISION_PERMISSIONS = {
    "CAN_AUTHORIZE",
    "CAN_INFORM_ONLY",
    "CAN_TEACH_ONLY",
    "MUST_REFRESH",
    "MUST_BLOCK",
    "UNKNOWN_PERMISSION",
}

DEFAULT_POLICIES: dict[str, dict[str, Any]] = {
    "MARKET_IDENTITY": {"ttl_seconds": 600, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "TOKEN_IDENTITY": {"ttl_seconds": 600, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "ORDERBOOK_SNAPSHOT": {"ttl_seconds": 180, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "TRUSTED_ORDERBOOK": {"ttl_seconds": 180, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "EXECUTABLE_PRICE": {"ttl_seconds": 180, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "RISK_DECISION": {"ttl_seconds": 600, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "EXIT_PLAN": {"ttl_seconds": 600, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "CAPITAL_EVALUATION": {"ttl_seconds": 600, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "PAYOUT_ODDS": {"ttl_seconds": 600, "criticality": "CONTEXT", "can_authorize_when_fresh": False, "stale_behavior": "LAST_KNOWN"},
    "EXIT_HOLD": {"ttl_seconds": 600, "criticality": "CONTEXT", "can_authorize_when_fresh": False, "stale_behavior": "LAST_KNOWN"},
    "CAPITAL_EFFICIENCY": {"ttl_seconds": 600, "criticality": "CONTEXT", "can_authorize_when_fresh": False, "stale_behavior": "LAST_KNOWN"},
    "TRADE_LIFECYCLE_PLAN": {"ttl_seconds": 600, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "LIFECYCLE_PLAN": {"ttl_seconds": 600, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "LIFECYCLE_GOVERNANCE": {"ttl_seconds": 600, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "SAME_MARKET_GUARD": {"ttl_seconds": 600, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "PAPER_INTENT": {"ttl_seconds": 600, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "PAPER_CANDIDATE": {"ttl_seconds": 600, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "REFRESH_REQUIRED"},
    "PAPER_POSITION_OPEN": {"ttl_seconds": None, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "UNKNOWN"},
    "PAPER_POSITION_CLOSED": {"ttl_seconds": None, "criticality": "HISTORICAL", "can_authorize_when_fresh": False, "stale_behavior": "HISTORICAL_ONLY"},
    "PAPER_CLOSE": {"ttl_seconds": None, "criticality": "HISTORICAL", "can_authorize_when_fresh": False, "stale_behavior": "HISTORICAL_ONLY"},
    "CAPITAL_LOCK": {"ttl_seconds": None, "criticality": "CRITICAL", "can_authorize_when_fresh": True, "stale_behavior": "UNKNOWN"},
    "CAPITAL_RELEASE": {"ttl_seconds": None, "criticality": "HISTORICAL", "can_authorize_when_fresh": False, "stale_behavior": "HISTORICAL_ONLY"},
    "CAPITAL_ACCOUNT_EVENT": {"ttl_seconds": None, "criticality": "HISTORICAL", "can_authorize_when_fresh": False, "stale_behavior": "HISTORICAL_ONLY"},
    "MESH_COORDINATOR": {"ttl_seconds": 600, "criticality": "CONTEXT", "can_authorize_when_fresh": False, "stale_behavior": "LAST_KNOWN"},
}


class TruthStateService:
    """Active truth and historical memory registry.

    This service writes derived truth-state rows only. It does not create Paper
    intents, orders, fills, positions, closes, capital ledger rows, or balances.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def register_truth(
        self,
        conn: Any,
        *,
        source_table: str,
        source_record_id: str,
        source_type: str,
        subject_type: str | None = None,
        subject_id: str | None = None,
        market_id: str | None = None,
        condition_id: str | None = None,
        side: str | None = None,
        token_id: str | None = None,
        created_at_source: Any = None,
        updated_at_source: Any = None,
        metadata: dict[str, Any] | None = None,
        write: bool = True,
    ) -> dict[str, Any]:
        source_type = str(source_type or "UNKNOWN").upper()
        metadata = metadata or {}
        truth_id = _truth_id(source_table, source_record_id, source_type)
        policy = _policy_for(conn, source_type)
        classification = self.classify_source(
            source_type=source_type,
            created_at_source=created_at_source,
            updated_at_source=updated_at_source,
            metadata=metadata,
            policy=policy,
        )
        existing = _fetchone(conn, "SELECT * FROM truth_state_registry WHERE truth_id=%s", (truth_id,)) if write and _table_exists(conn, "truth_state_registry") else None
        row = {
            "truth_id": truth_id,
            "source_table": source_table,
            "source_record_id": str(source_record_id),
            "source_type": source_type,
            "subject_type": _nullable_text(subject_type),
            "subject_id": _nullable_text(subject_id),
            "market_id": _nullable_text(market_id),
            "condition_id": _nullable_text(condition_id),
            "side": _nullable_text(side).upper() if _nullable_text(side) else None,
            "token_id": _nullable_text(token_id),
            "created_at_source": _datetime_or_none(created_at_source),
            "updated_at_source": _datetime_or_none(updated_at_source),
            "last_verified_at": datetime.now(UTC),
            **classification,
            "metadata_json": metadata,
        }
        row["is_current_for_subject"] = bool(row["subject_id"] and row["truth_state"] == "ACTIVE_FRESH")
        row["is_current_for_market"] = bool(row["market_id"] and row["truth_state"] == "ACTIVE_FRESH")
        row["is_historical_memory"] = row["truth_state"] == "HISTORICAL_ONLY" or row["decision_permission"] == "CAN_TEACH_ONLY"
        row["previous_truth_id"] = None
        row["superseded_by_truth_id"] = None
        if write and _table_exists(conn, "truth_state_registry"):
            previous_truth_id = _previous_current_truth(conn, row)
            row["previous_truth_id"] = previous_truth_id if previous_truth_id != truth_id else None
            _supersede_previous_current_truth(conn, row)
            _upsert_truth(conn, row)
            if existing is None or existing.get("truth_state") != row["truth_state"] or existing.get("decision_permission") != row["decision_permission"]:
                _insert_transition(
                    conn,
                    truth_id=truth_id,
                    previous_state=(existing or {}).get("truth_state"),
                    new_state=row["truth_state"],
                    previous_permission=(existing or {}).get("decision_permission"),
                    new_permission=row["decision_permission"],
                    reason=row["freshness_reason"],
                    source_table=source_table,
                    source_record_id=str(source_record_id),
                )
        return _json_safe(row)

    def classify_source(
        self,
        *,
        source_type: str,
        created_at_source: Any = None,
        updated_at_source: Any = None,
        metadata: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        source_type = str(source_type or "UNKNOWN").upper()
        policy = policy or DEFAULT_POLICIES.get(source_type, {})
        policy.setdefault("ttl_seconds", None)
        policy.setdefault("criticality", "CONTEXT")
        policy.setdefault("can_authorize_when_fresh", False)
        policy.setdefault("stale_behavior", "LAST_KNOWN")
        effective_at = _datetime_or_none(updated_at_source) or _datetime_or_none(created_at_source)
        age = _age_seconds(effective_at)

        forced = _forced_state(source_type, metadata)
        if forced:
            state, permission, reason = forced
        elif effective_at is None:
            state = "UNKNOWN"
            permission = "MUST_BLOCK" if policy["criticality"] == "CRITICAL" else "UNKNOWN_PERMISSION"
            reason = f"{source_type} timestamp is missing; authorization is unknown."
        elif policy["ttl_seconds"] is None:
            if policy["criticality"] == "HISTORICAL":
                state = "HISTORICAL_ONLY"
                permission = "CAN_TEACH_ONLY"
                reason = f"{source_type} is historical memory by policy."
            else:
                state = "ACTIVE_FRESH"
                permission = "CAN_AUTHORIZE" if policy["can_authorize_when_fresh"] else "CAN_INFORM_ONLY"
                reason = f"{source_type} has no TTL and remains active while source row is active."
        elif age is not None and age <= int(policy["ttl_seconds"]):
            state = "ACTIVE_FRESH"
            permission = "CAN_AUTHORIZE" if policy["can_authorize_when_fresh"] else "CAN_INFORM_ONLY"
            reason = f"{source_type} is fresh at age {age}s <= TTL {policy['ttl_seconds']}s."
        else:
            behavior = str(policy.get("stale_behavior") or "LAST_KNOWN").upper()
            if behavior == "REFRESH_REQUIRED":
                state = "REFRESH_REQUIRED"
                permission = "MUST_REFRESH"
                reason = f"{source_type} is stale/expired and must refresh before authorization."
            elif behavior == "HISTORICAL_ONLY":
                state = "HISTORICAL_ONLY"
                permission = "CAN_TEACH_ONLY"
                reason = f"{source_type} is stale and retained only as historical memory."
            elif behavior == "UNKNOWN":
                state = "UNKNOWN"
                permission = "UNKNOWN_PERMISSION"
                reason = f"{source_type} is stale and policy cannot determine authorization."
            else:
                state = "LAST_KNOWN"
                permission = "CAN_INFORM_ONLY"
                reason = f"{source_type} is stale but may inform as last-known context."

        return {
            "truth_state": state,
            "decision_permission": permission,
            "ttl_seconds": policy.get("ttl_seconds"),
            "age_seconds": age,
            "freshness_reason": reason,
        }

    def decision_permission_for_source(
        self,
        conn: Any,
        *,
        source_table: str,
        source_record_id: str | None,
        source_type: str,
        timestamp: Any = None,
        metadata: dict[str, Any] | None = None,
        write: bool = False,
    ) -> dict[str, Any]:
        if not source_record_id:
            classification = self.classify_source(source_type=source_type, metadata={"missing_source": True, **(metadata or {})})
            return _json_safe({"source_table": source_table, "source_record_id": source_record_id, "source_type": source_type, **classification})
        existing = None
        if _table_exists(conn, "truth_state_registry"):
            existing = _fetchone(
                conn,
                """
                SELECT *
                FROM truth_state_registry
                WHERE source_table=%s AND source_record_id=%s AND source_type=%s
                ORDER BY updated_at DESC,id DESC LIMIT 1
                """,
                (source_table, str(source_record_id), str(source_type).upper()),
            )
        if existing and not write:
            return _json_safe(existing)
        return self.register_truth(
            conn,
            source_table=source_table,
            source_record_id=str(source_record_id),
            source_type=source_type,
            created_at_source=timestamp,
            updated_at_source=timestamp,
            metadata=metadata or {},
            write=write,
        )

    def audit_current_db(self, *, limit: int = 100, dry_run: bool = False) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return _empty("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "truth_state_registry"):
                return _empty("MISSING_TRUTH_TABLES", generated_at)
            before = _count_table(conn, "truth_state_registry")
            safety_before = _safety_counts(conn)
            rows = []
            rows.extend(self._audit_table(conn, "same_market_side_guard_decisions", "decision_id", "SAME_MARKET_GUARD", "created_at", limit=limit))
            rows.extend(self._audit_table(conn, "trade_lifecycle_plans", "plan_id", "LIFECYCLE_PLAN", "updated_at", limit=limit))
            rows.extend(self._audit_table(conn, "lifecycle_governance_decisions", "decision_id", "LIFECYCLE_GOVERNANCE", "created_at", limit=limit))
            rows.extend(self._audit_table(conn, "risk_decisions", "risk_decision_id", "RISK_DECISION", "updated_at", limit=limit))
            rows.extend(self._audit_table(conn, "exit_plans", "exit_plan_id", "EXIT_PLAN", "updated_at", limit=limit))
            rows.extend(self._audit_table(conn, "capital_brain_evaluations", "evaluation_id", "CAPITAL_EVALUATION", "created_at", limit=limit))
            rows.extend(self._audit_table(conn, "payout_odds_evaluations", "evaluation_id", "PAYOUT_ODDS", "created_at", limit=limit))
            rows.extend(self._audit_table(conn, "exit_hold_evaluations", "evaluation_id", "EXIT_HOLD", "created_at", limit=limit))
            rows.extend(self._audit_table(conn, "capital_efficiency_evaluations", "evaluation_id", "CAPITAL_EFFICIENCY", "updated_at", limit=limit))
            rows.extend(self._audit_table(conn, "orderbook_snapshots", "id", "ORDERBOOK_SNAPSHOT", "COALESCE(snapshot_at,collected_at,created_at)", limit=limit))
            rows.extend(self._audit_paper_intents(conn, limit=limit))
            rows.extend(self._audit_paper_positions(conn, limit=limit))
            rows.extend(self._audit_capital_ledger(conn, limit=limit))

            outcomes = [
                self.register_truth(conn, write=not dry_run, **row)
                for row in rows[: max(0, limit * 16)]
            ]
            after = _count_table(conn, "truth_state_registry")
            safety_after = _safety_counts(conn)
        state_counts = Counter(item["truth_state"] for item in outcomes)
        permission_counts = Counter(item["decision_permission"] for item in outcomes)
        return _json_safe(
            {
                "mock_data": False,
                "status": "DRY_RUN" if dry_run else "OK",
                "generated_at": generated_at,
                "records_checked": len(outcomes),
                "truth_rows_created": 0 if dry_run else max(0, after - before),
                "truth_state_counts": dict(state_counts),
                "decision_permission_counts": dict(permission_counts),
                "latest_outcomes": outcomes[:20],
                "safety_before": safety_before,
                "safety_after": safety_after,
                "trading_mutation": safety_before != safety_after,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
            }
        )

    def dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return _empty("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn:
            if not _table_exists(conn, "truth_state_registry"):
                return _empty("MISSING_TRUTH_TABLES", generated_at)
            totals = _fetchone(conn, "SELECT COUNT(*) AS total FROM truth_state_registry") or {}
            states = _fetchall(conn, "SELECT truth_state, COUNT(*) AS count FROM truth_state_registry GROUP BY truth_state ORDER BY count DESC, truth_state")
            permissions = _fetchall(conn, "SELECT decision_permission, COUNT(*) AS count FROM truth_state_registry GROUP BY decision_permission ORDER BY count DESC, decision_permission")
            by_source = _fetchall(conn, "SELECT source_type, truth_state, COUNT(*) AS count FROM truth_state_registry GROUP BY source_type, truth_state ORDER BY count DESC, source_type LIMIT %s", (limit,))
            latest = _fetchall(conn, "SELECT * FROM truth_state_registry ORDER BY updated_at DESC,id DESC LIMIT %s", (limit,))
            refresh_required = _count_where(conn, "truth_state_registry", "truth_state='REFRESH_REQUIRED' OR decision_permission='MUST_REFRESH'")
            historical = _count_where(conn, "truth_state_registry", "truth_state='HISTORICAL_ONLY' OR is_historical_memory")
            can_authorize = _count_where(conn, "truth_state_registry", "decision_permission='CAN_AUTHORIZE'")
            stale_same_market = _count_where(conn, "truth_state_registry", "source_type='SAME_MARKET_GUARD' AND decision_permission <> 'CAN_AUTHORIZE'")
            old_intents = _count_where(conn, "truth_state_registry", "source_type='PAPER_INTENT' AND decision_permission <> 'CAN_AUTHORIZE'")
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "total_truth_records": _int(totals.get("total")),
                "truth_state_counts": {str(row["truth_state"]): _int(row["count"]) for row in states},
                "decision_permission_counts": {str(row["decision_permission"]): _int(row["count"]) for row in permissions},
                "source_state_counts": by_source,
                "can_authorize_count": can_authorize,
                "refresh_required_count": refresh_required,
                "historical_memory_count": historical,
                "stale_same_market_guard_count": stale_same_market,
                "old_intents_requiring_refresh": old_intents,
                "latest_truth": latest,
            }
        )

    def detail(self, truth_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "truth_id": truth_id}
        with self._factory.connect() as conn:
            if not _table_exists(conn, "truth_state_registry"):
                return {"mock_data": False, "status": "MISSING_TRUTH_TABLES", "truth_id": truth_id}
            truth = _fetchone(conn, "SELECT * FROM truth_state_registry WHERE truth_id=%s", (truth_id,))
            if not truth:
                return {"mock_data": False, "status": "NOT_FOUND", "truth_id": truth_id}
            transitions = _fetchall(conn, "SELECT * FROM truth_state_transitions WHERE truth_id=%s ORDER BY created_at DESC,id DESC", (truth_id,)) if _table_exists(conn, "truth_state_transitions") else []
            links = _fetchall(conn, "SELECT * FROM truth_state_decision_links WHERE truth_id=%s ORDER BY linked_at DESC,id DESC", (truth_id,)) if _table_exists(conn, "truth_state_decision_links") else []
        return _json_safe({"mock_data": False, "status": "OK", "truth": truth, "transitions": transitions, "decision_links": links})

    def subject_detail(self, subject_id: str, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "subject_id": subject_id}
        with self._factory.connect() as conn:
            if not _table_exists(conn, "truth_state_registry"):
                return {"mock_data": False, "status": "MISSING_TRUTH_TABLES", "subject_id": subject_id}
            rows = _fetchall(
                conn,
                """
                SELECT *
                FROM truth_state_registry
                WHERE subject_id=%s OR source_record_id=%s OR market_id=%s
                ORDER BY updated_at DESC,id DESC
                LIMIT %s
                """,
                (subject_id, subject_id, subject_id, limit),
            )
        return _json_safe({"mock_data": False, "status": "OK", "subject_id": subject_id, "truth_records": rows})

    def _audit_table(self, conn: Any, table: str, id_column: str, source_type: str, timestamp_column: str, *, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, table) or not _column_exists(conn, table, id_column.split("::")[0]):
            return []
        rows = _fetchall(
            conn,
            f"""
            SELECT *, {id_column}::text AS source_record_id, {timestamp_column} AS source_at
            FROM {table}
            ORDER BY {timestamp_column} DESC NULLS LAST, id DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [_row_to_truth(table, source_type, row, row.get("source_at")) for row in rows]

    def _audit_paper_intents(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_intents"):
            return []
        rows = _fetchall(conn, "SELECT *, paper_intent_id AS source_record_id, COALESCE(updated_at,created_at) AS source_at FROM paper_intents ORDER BY COALESCE(updated_at,created_at) DESC NULLS LAST,id DESC LIMIT %s", (limit,))
        return [_row_to_truth("paper_intents", "PAPER_INTENT", row, row.get("source_at"), subject_type="PAPER_INTENT", subject_id=row.get("paper_intent_id")) for row in rows]

    def _audit_paper_positions(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_positions"):
            return []
        rows = _fetchall(conn, "SELECT *, id::text AS source_record_id, COALESCE(updated_at,closed_at,opened_at) AS source_at FROM paper_positions ORDER BY COALESCE(updated_at,closed_at,opened_at) DESC NULLS LAST,id DESC LIMIT %s", (limit,))
        out = []
        for row in rows:
            closed = bool(row.get("closed_at")) or str(row.get("current_status") or "").upper() not in {"OPEN", "EXIT_PENDING"}
            out.append(_row_to_truth("paper_positions", "PAPER_POSITION_CLOSED" if closed else "PAPER_POSITION_OPEN", row, row.get("source_at"), subject_type="PAPER_POSITION", subject_id=row.get("source_record_id"), metadata={"current_status": row.get("current_status"), "closed": closed}))
        return out

    def _audit_capital_ledger(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_capital_ledger"):
            return []
        rows = _fetchall(conn, "SELECT *, COALESCE(ledger_id,id::text) AS source_record_id, created_at AS source_at FROM paper_capital_ledger ORDER BY created_at DESC,id DESC LIMIT %s", (limit,))
        out = []
        for row in rows:
            event = str(row.get("event_type") or "").upper()
            if "LOCKED" in event or "LOCK_BACKFILLED" in event:
                source_type = "CAPITAL_LOCK"
            elif "RELEASE" in event or "REALIZED_PNL" in event or "UNREALIZED_PNL" in event:
                source_type = "CAPITAL_RELEASE"
            else:
                source_type = "CAPITAL_ACCOUNT_EVENT"
            out.append(_row_to_truth("paper_capital_ledger", source_type, row, row.get("source_at"), subject_type="PAPER_POSITION", subject_id=row.get("paper_position_id"), metadata={"event_type": event}))
        return out


def _row_to_truth(
    source_table: str,
    source_type: str,
    row: dict[str, Any],
    source_at: Any,
    *,
    subject_type: str | None = None,
    subject_id: Any = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    subject_type = subject_type or row.get("subject_type")
    subject_id = subject_id or row.get("subject_id") or row.get("eligibility_id") or row.get("paper_intent_id")
    return {
        "source_table": source_table,
        "source_record_id": str(row.get("source_record_id") or row.get("id") or ""),
        "source_type": source_type,
        "subject_type": _nullable_text(subject_type),
        "subject_id": _nullable_text(subject_id),
        "market_id": _nullable_text(row.get("market_id")),
        "condition_id": _nullable_text(row.get("condition_id")),
        "side": _nullable_text(row.get("side") or row.get("intended_outcome") or row.get("proposed_side")),
        "token_id": _nullable_text(row.get("token_id")),
        "created_at_source": row.get("created_at") or source_at,
        "updated_at_source": row.get("updated_at") or source_at,
        "metadata": {"source_status": row.get("status") or row.get("decision") or row.get("intent_status"), **(metadata or {})},
    }


def _forced_state(source_type: str, metadata: dict[str, Any]) -> tuple[str, str, str] | None:
    if source_type == "PAPER_POSITION_CLOSED" or metadata.get("closed") is True:
        return "HISTORICAL_ONLY", "CAN_TEACH_ONLY", "Closed Paper position is historical memory and cannot authorize new action."
    if source_type == "PAPER_CLOSE":
        return "HISTORICAL_ONLY", "CAN_TEACH_ONLY", "Paper close is historical memory and cannot authorize new action."
    if source_type == "CAPITAL_RELEASE":
        return "HISTORICAL_ONLY", "CAN_TEACH_ONLY", "Capital release is accounting history and cannot authorize new action."
    if source_type == "CAPITAL_ACCOUNT_EVENT":
        return "HISTORICAL_ONLY", "CAN_TEACH_ONLY", "Capital account event is accounting history and cannot authorize new action."
    if metadata.get("missing_source") is True:
        return "UNKNOWN", "MUST_BLOCK", f"{source_type} source is missing."
    return None


def _policy_for(conn: Any, source_type: str) -> dict[str, Any]:
    if _table_exists(conn, "truth_state_policy"):
        row = _fetchone(conn, "SELECT * FROM truth_state_policy WHERE source_type=%s", (source_type,))
        if row:
            return row
    return dict(DEFAULT_POLICIES.get(source_type, {"ttl_seconds": None, "criticality": "CONTEXT", "can_authorize_when_fresh": False, "stale_behavior": "LAST_KNOWN"}))


def _previous_current_truth(conn: Any, row: dict[str, Any]) -> str | None:
    if not row.get("subject_id") or row["truth_state"] != "ACTIVE_FRESH":
        return None
    previous = _fetchone(
        conn,
        """
        SELECT truth_id
        FROM truth_state_registry
        WHERE subject_type IS NOT DISTINCT FROM %s
          AND subject_id=%s
          AND source_type=%s
          AND is_current_for_subject=true
          AND truth_id<>%s
        ORDER BY updated_at DESC,id DESC LIMIT 1
        """,
        (row.get("subject_type"), row["subject_id"], row["source_type"], row["truth_id"]),
    )
    return (previous or {}).get("truth_id")


def _supersede_previous_current_truth(conn: Any, row: dict[str, Any]) -> None:
    if not row.get("subject_id") or row["truth_state"] != "ACTIVE_FRESH":
        return
    conn.execute(
        """
        UPDATE truth_state_registry
        SET is_current_for_subject=false,
            is_current_for_market=false,
            superseded_by_truth_id=%s,
            truth_state=CASE WHEN truth_state='ACTIVE_FRESH' THEN 'LAST_KNOWN' ELSE truth_state END,
            decision_permission=CASE WHEN decision_permission='CAN_AUTHORIZE' THEN 'CAN_INFORM_ONLY' ELSE decision_permission END,
            updated_at=now()
        WHERE source_type=%s
          AND truth_id<>%s
          AND (
              (subject_id IS NOT NULL AND subject_id=%s)
              OR (market_id IS NOT NULL AND market_id IS NOT DISTINCT FROM %s)
          )
          AND (is_current_for_subject=true OR is_current_for_market=true)
        """,
        (row["truth_id"], row["source_type"], row["truth_id"], row.get("subject_id"), row.get("market_id")),
    )


def _upsert_truth(conn: Any, row: dict[str, Any]) -> None:
    params = {**row, "metadata_json": Jsonb(_json_safe(row.get("metadata_json") or {}))}
    conn.execute(
        """
        INSERT INTO truth_state_registry (
            truth_id,source_table,source_record_id,source_type,subject_type,subject_id,market_id,condition_id,side,token_id,
            truth_state,decision_permission,created_at_source,updated_at_source,last_verified_at,ttl_seconds,age_seconds,
            freshness_reason,previous_truth_id,superseded_by_truth_id,is_current_for_subject,is_current_for_market,
            is_historical_memory,metadata_json
        )
        VALUES (
            %(truth_id)s,%(source_table)s,%(source_record_id)s,%(source_type)s,%(subject_type)s,%(subject_id)s,%(market_id)s,%(condition_id)s,%(side)s,%(token_id)s,
            %(truth_state)s,%(decision_permission)s,%(created_at_source)s,%(updated_at_source)s,%(last_verified_at)s,%(ttl_seconds)s,%(age_seconds)s,
            %(freshness_reason)s,%(previous_truth_id)s,%(superseded_by_truth_id)s,%(is_current_for_subject)s,%(is_current_for_market)s,
            %(is_historical_memory)s,%(metadata_json)s
        )
        ON CONFLICT (source_table, source_record_id, source_type) DO UPDATE SET
            subject_type=EXCLUDED.subject_type,
            subject_id=EXCLUDED.subject_id,
            market_id=EXCLUDED.market_id,
            condition_id=EXCLUDED.condition_id,
            side=EXCLUDED.side,
            token_id=EXCLUDED.token_id,
            truth_state=EXCLUDED.truth_state,
            decision_permission=EXCLUDED.decision_permission,
            created_at_source=EXCLUDED.created_at_source,
            updated_at_source=EXCLUDED.updated_at_source,
            last_verified_at=EXCLUDED.last_verified_at,
            ttl_seconds=EXCLUDED.ttl_seconds,
            age_seconds=EXCLUDED.age_seconds,
            freshness_reason=EXCLUDED.freshness_reason,
            previous_truth_id=EXCLUDED.previous_truth_id,
            is_current_for_subject=EXCLUDED.is_current_for_subject,
            is_current_for_market=EXCLUDED.is_current_for_market,
            is_historical_memory=EXCLUDED.is_historical_memory,
            metadata_json=EXCLUDED.metadata_json,
            updated_at=now()
        """,
        params,
    )


def _insert_transition(
    conn: Any,
    *,
    truth_id: str,
    previous_state: str | None,
    new_state: str,
    previous_permission: str | None,
    new_permission: str,
    reason: str,
    source_table: str,
    source_record_id: str,
) -> None:
    raw = "|".join([truth_id, str(previous_state), new_state, str(previous_permission), new_permission, reason])
    conn.execute(
        """
        INSERT INTO truth_state_transitions (
            transition_id,truth_id,previous_state,new_state,previous_permission,new_permission,
            reason,triggered_by_source_table,triggered_by_source_record_id
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (transition_id) DO NOTHING
        """,
        (f"truth_transition_{uuid5(NAMESPACE_URL, raw).hex}", truth_id, previous_state, new_state, previous_permission, new_permission, reason, source_table, source_record_id),
    )


def _truth_id(source_table: str, source_record_id: str, source_type: str) -> str:
    return f"truth_{uuid5(NAMESPACE_URL, '|'.join([source_table, str(source_record_id), source_type])).hex}"


def _age_seconds(timestamp: datetime | None) -> int | None:
    if timestamp is None:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - timestamp.astimezone(UTC)).total_seconds()))


def _datetime_or_none(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _nullable_text(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    return str(value)


def _fetchone(conn: Any, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _column_exists(conn: Any, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = ANY(current_schemas(false))
              AND table_name=%s
              AND column_name=%s
            LIMIT 1
            """,
            (table, column),
        ).fetchone()
    )


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"])


def _safety_counts(conn: Any) -> dict[str, Any]:
    counts = {
        table: _count_table(conn, table)
        for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "paper_capital_ledger", "live_orders", "orders_v2", "fills_v2", "positions")
    }
    account = _fetchone(conn, "SELECT current_balance,available_balance,locked_balance,open_exposure,realized_pnl,unrealized_pnl FROM paper_accounts WHERE account_id='paper_default'") if _table_exists(conn, "paper_accounts") else None
    counts["capital_balances"] = _json_safe(account) if account else None
    return counts


def _empty(status: str, generated_at: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "generated_at": generated_at,
        "security_governance_status": SECURITY_GOVERNANCE_STATUS,
        "total_truth_records": 0,
        "truth_state_counts": {},
        "decision_permission_counts": {},
        "latest_truth": [],
    }


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
