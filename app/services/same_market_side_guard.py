from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_session import active_paper_session_id


ALLOWED_RATIONALES = {
    "HEDGE_RATIONALE",
    "ARBITRAGE_RATIONALE",
    "PARTIAL_EXIT_RATIONALE",
    "MARKET_MAKING_RATIONALE",
    "EXPOSURE_REDUCTION_RATIONALE",
    "POSITION_REPAIR_RATIONALE",
}

OPPOSITE_SIDE = {"YES": "NO", "NO": "YES"}
ACTIVE_INTENT_STATUSES = {"CREATED", "READY", "EXECUTING"}
RECENT_CLOSE_WINDOW = timedelta(minutes=45)
ACTIVE_INTENT_FRESHNESS_WINDOW = timedelta(minutes=10)
SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"


@dataclass(frozen=True)
class SameMarketSideGuardDecision:
    decision_id: str
    market_id: str
    proposed_side: str
    proposed_candidate_id: str | None
    proposed_intent_id: str | None
    existing_exposure: dict[str, Any]
    existing_open_positions_count: int
    existing_opposite_positions_count: int
    existing_same_side_positions_count: int
    existing_opposite_intents_count: int
    existing_same_side_intents_count: int
    recent_opposite_closes_count: int
    batch_opposite_candidates_count: int
    rationale_type: str | None
    rationale_source: str | None
    source_backed: bool
    decision: str
    blocker_reason: str | None
    dry_run: bool = False

    @property
    def allowed(self) -> bool:
        return self.decision == "ALLOW"

    def to_api_dict(self) -> dict[str, Any]:
        return _json_safe(self.__dict__)


class SameMarketSideGuardService:
    """Coherence guard for same-market YES/NO paper exposure.

    The guard is source-backed and conservative: it blocks or sends to review
    unless a coordinator/mesh/thesis source explicitly records an allowed
    strategic rationale.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def evaluate(
        self,
        conn: Any,
        *,
        market_id: str,
        proposed_side: str,
        proposed_candidate_id: str | None = None,
        proposed_intent_id: str | None = None,
        coordinator_decision_id: str | None = None,
        evidence: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        batch_sides: dict[str, set[str]] | None = None,
        write_decision: bool = True,
        dry_run: bool = False,
    ) -> SameMarketSideGuardDecision:
        side = str(proposed_side or "").upper()
        if side not in OPPOSITE_SIDE:
            return self._build_decision(
                conn,
                market_id=str(market_id or ""),
                proposed_side=side,
                proposed_candidate_id=proposed_candidate_id,
                proposed_intent_id=proposed_intent_id,
                existing_exposure={},
                rationale=(None, None, False),
                decision="BLOCK",
                blocker_reason="INVALID_SIDE",
                dry_run=dry_run,
                metadata=metadata,
                write_decision=write_decision,
            )
        exposure = self._existing_exposure(
            conn,
            market_id=str(market_id),
            proposed_side=side,
            proposed_intent_id=proposed_intent_id,
            batch_sides=batch_sides,
            metadata=metadata,
        )
        rationale = self._source_backed_rationale(
            conn,
            coordinator_decision_id=coordinator_decision_id,
            evidence=evidence or {},
            metadata=metadata or {},
        )
        rationale_type, rationale_source, source_backed = rationale
        decision = "ALLOW"
        blocker_reason: str | None = None
        if (exposure["opposite_open_positions"] or exposure["opposite_active_intents"] or exposure["batch_opposite_candidates"]) and not source_backed:
            decision = "BLOCK"
            if exposure["opposite_open_positions"]:
                blocker_reason = "SAME_MARKET_OPEN_OPPOSITE_POSITION_BLOCK"
            elif exposure["opposite_active_intents"]:
                blocker_reason = "SAME_MARKET_ACTIVE_OPPOSITE_INTENT_BLOCK"
            else:
                blocker_reason = "SAME_MARKET_BATCH_CONFLICT_BLOCK"
        elif (exposure["opposite_open_positions"] or exposure["opposite_active_intents"] or exposure["batch_opposite_candidates"]) and source_backed:
            decision = "ALLOW"
        elif exposure["same_side_open_positions"] or exposure["same_side_active_intents"]:
            decision = "REVIEW"
            blocker_reason = "SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW"
        elif exposure["recent_opposite_closes"]:
            decision = "REVIEW"
            blocker_reason = "SAME_MARKET_RECENT_OPPOSING_SIDE_REVIEW"

        return self._build_decision(
            conn,
            market_id=str(market_id),
            proposed_side=side,
            proposed_candidate_id=proposed_candidate_id,
            proposed_intent_id=proposed_intent_id,
            existing_exposure=exposure,
            rationale=(rationale_type, rationale_source, source_backed),
            decision=decision,
            blocker_reason=blocker_reason,
            dry_run=dry_run,
            metadata=metadata,
            write_decision=write_decision,
        )

    def get_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard()
        with self._factory.connect() as conn:
            if not _table_exists(conn, "same_market_side_guard_decisions"):
                return _empty_dashboard(status="MISSING_GUARD_TABLE")
            counts = _fetchone(
                conn,
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE decision = 'BLOCK') AS blocked,
                    COUNT(*) FILTER (WHERE decision = 'REVIEW') AS review,
                    COUNT(*) FILTER (WHERE decision = 'ALLOW') AS allowed,
                    COUNT(*) FILTER (WHERE blocker_reason IN ('SAME_MARKET_OPPOSING_SIDE_BLOCK', 'SAME_MARKET_OPPOSING_INTENT_BLOCK')) AS opposing_blocks,
                    COUNT(*) FILTER (WHERE blocker_reason = 'SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW') AS duplicate_reviews
                FROM same_market_side_guard_decisions
                """,
            ) or {}
            latest = _fetchall(
                conn,
                """
                SELECT *
                FROM same_market_side_guard_decisions
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            )
            both_sides = self._markets_with_both_sides(conn, limit=limit)
            traces = self._sample_traces(conn, limit=limit)
        blocked = _int(counts.get("blocked"))
        review = _int(counts.get("review"))
        guard_status = "RED" if blocked else "REVIEW" if review else "OK"
        return _json_safe(
            {
                "mock_data": False,
                "guard_status": guard_status,
                "total_guard_decisions": _int(counts.get("total")),
                "blocked_count": blocked,
                "review_count": review,
                "allowed_count": _int(counts.get("allowed")),
                "opposing_side_blocks": _int(counts.get("opposing_blocks")),
                "duplicate_exposure_reviews": _int(counts.get("duplicate_reviews")),
                "markets_with_both_sides": both_sides,
                "latest_decisions": latest,
                "sample_same_market_traces": traces,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "last_updated": datetime.now(UTC).isoformat(),
            }
        )

    def get_market_detail(self, market_id: str, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "market_id": market_id}
        with self._factory.connect() as conn:
            exposure = self._existing_exposure(conn, market_id=str(market_id), proposed_side="YES")
            decisions = _fetchall(
                conn,
                """
                SELECT *
                FROM same_market_side_guard_decisions
                WHERE market_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (str(market_id), limit),
            ) if _table_exists(conn, "same_market_side_guard_decisions") else []
            positions = _fetchall(
                conn,
                """
                SELECT id::text AS paper_position_id, market_id, intended_outcome AS side,
                       current_status, opened_at, closed_at, payload_json
                FROM paper_positions
                WHERE market_id = %s
                ORDER BY opened_at DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (str(market_id), limit),
            ) if _table_exists(conn, "paper_positions") else []
            intents = _fetchall(
                conn,
                """
                SELECT paper_intent_id, eligibility_id, market_id, side, intent_status,
                       coordinator_decision_id, evidence, created_at, updated_at
                FROM paper_intents
                WHERE market_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (str(market_id), limit),
            ) if _table_exists(conn, "paper_intents") else []
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "market_id": str(market_id),
                "existing_exposure": exposure,
                "guard_decisions": decisions,
                "paper_positions": positions,
                "paper_intents": intents,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
            }
        )

    def _existing_exposure(
        self,
        conn: Any,
        *,
        market_id: str,
        proposed_side: str,
        proposed_intent_id: str | None = None,
        batch_sides: dict[str, set[str]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        opposite = OPPOSITE_SIDE[proposed_side]
        active_session = active_paper_session_id(conn)
        position_session_clause = "AND (%s::text IS NULL OR paper_session_id = %s::text)" if _column_exists(conn, "paper_positions", "paper_session_id") else "AND %s::text IS NULL AND %s::text IS NULL"
        open_positions = _fetchall(
            conn,
            f"""
            SELECT id::text AS paper_position_id, market_id, intended_outcome AS side,
                   avg_entry, size, (avg_entry * size) AS notional, opened_at, payload_json
            FROM paper_positions
            WHERE market_id = %s
              AND current_status = 'OPEN'
              AND closed_at IS NULL
              AND COALESCE(excluded_from_active_paper_truth, false) = false
              {position_session_clause}
            ORDER BY opened_at DESC NULLS LAST, id DESC
            """,
            (market_id, active_session, active_session),
        ) if _table_exists(conn, "paper_positions") else []
        active_intents = self._active_intents(conn, market_id=market_id, proposed_intent_id=proposed_intent_id, paper_session_id=active_session)
        stale_active_intents = self._stale_active_intents(conn, market_id=market_id, proposed_intent_id=proposed_intent_id, paper_session_id=active_session)
        recent_closes = self._recent_opposite_closes(conn, market_id=market_id, opposite_side=opposite, metadata=metadata or {})
        active_locks = _fetchall(
            conn,
            """
            SELECT *
            FROM position_token_locks
            WHERE market_id = %s
              AND status IN ('ACTIVE', 'OPEN', 'LOCKED')
            ORDER BY locked_at DESC NULLS LAST, id DESC
            """,
            (market_id,),
        ) if _table_exists(conn, "position_token_locks") else []
        active_capital = _fetchall(
            conn,
            """
            SELECT pcl.paper_position_id, SUM(
                CASE
                    WHEN pcl.event_type IN ('CAPITAL_LOCKED_ON_FILL', 'CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL') THEN pcl.amount
                    WHEN pcl.event_type IN ('CAPITAL_RELEASED_ON_CLOSE', 'CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE') THEN -pcl.amount
                    ELSE 0
                END
            ) AS active_lock
            FROM paper_capital_ledger pcl
            JOIN paper_positions pp ON pp.id::text = pcl.paper_position_id
            WHERE pp.market_id = %s
            GROUP BY pcl.paper_position_id
            HAVING SUM(
                CASE
                    WHEN pcl.event_type IN ('CAPITAL_LOCKED_ON_FILL', 'CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL') THEN pcl.amount
                    WHEN pcl.event_type IN ('CAPITAL_RELEASED_ON_CLOSE', 'CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE') THEN -pcl.amount
                    ELSE 0
                END
            ) > 0
            """,
            (market_id,),
        ) if _table_exists(conn, "paper_capital_ledger") and _table_exists(conn, "paper_positions") else []
        sides = batch_sides.get(market_id, set()) if batch_sides else set()
        return {
            "market_id": market_id,
            "proposed_side": proposed_side,
            "opposite_side": opposite,
            "open_positions": open_positions,
            "opposite_open_positions": [row for row in open_positions if str(row.get("side")).upper() == opposite],
            "same_side_open_positions": [row for row in open_positions if str(row.get("side")).upper() == proposed_side],
            "active_intents": active_intents,
            "opposite_active_intents": [row for row in active_intents if str(row.get("side")).upper() == opposite],
            "same_side_active_intents": [row for row in active_intents if str(row.get("side")).upper() == proposed_side],
            "stale_active_intents": stale_active_intents,
            "stale_opposite_intents": [row for row in stale_active_intents if str(row.get("side")).upper() == opposite],
            "stale_same_side_intents": [row for row in stale_active_intents if str(row.get("side")).upper() == proposed_side],
            "recent_opposite_closes": recent_closes,
            "active_token_locks": active_locks,
            "active_capital_locks": active_capital,
            "batch_sides": sorted(sides),
            "batch_opposite_candidates": [opposite] if opposite in sides and proposed_side in sides else [],
        }

    def _active_intents(self, conn: Any, *, market_id: str, proposed_intent_id: str | None, paper_session_id: str | None = None) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_intents"):
            return []
        exclude_clause = ""
        params: list[Any] = [market_id, list(ACTIVE_INTENT_STATUSES)]
        if proposed_intent_id:
            exclude_clause = "AND pi.paper_intent_id <> %s"
            params.append(proposed_intent_id)
        session_clause = "AND (%s::text IS NULL OR pi.paper_session_id = %s::text)" if _column_exists(conn, "paper_intents", "paper_session_id") else "AND %s::text IS NULL AND %s::text IS NULL"
        return _fetchall(
            conn,
            f"""
            SELECT paper_intent_id, eligibility_id, market_id, side, intent_status, coordinator_decision_id, created_at
            FROM paper_intents pi
            WHERE pi.market_id = %s
              AND pi.intent_status = ANY(%s)
              AND pi.intent_type = 'PAPER_ENTRY_INTENT'
              AND pi.paper_only = true
              AND pi.live = false
              AND COALESCE(pi.is_dry_run_generated, false) = false
              AND COALESCE(pi.updated_at, pi.created_at) >= %s
              {session_clause}
              {exclude_clause}
              AND NOT EXISTS (SELECT 1 FROM paper_fills pf WHERE pf.source_intent_id = pi.paper_intent_id)
              AND NOT EXISTS (SELECT 1 FROM paper_positions pp WHERE pp.payload_json->>'source_intent_id' = pi.paper_intent_id)
              AND NOT EXISTS (SELECT 1 FROM paper_orders po WHERE po.payload_json->>'source_intent_id' = pi.paper_intent_id)
            ORDER BY pi.created_at DESC, pi.id DESC
            """,
            tuple([*params[:2], datetime.now(UTC) - ACTIVE_INTENT_FRESHNESS_WINDOW, paper_session_id, paper_session_id, *params[2:]]),
        )

    def _stale_active_intents(self, conn: Any, *, market_id: str, proposed_intent_id: str | None, paper_session_id: str | None = None) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_intents"):
            return []
        exclude_clause = ""
        params: list[Any] = [market_id, list(ACTIVE_INTENT_STATUSES), datetime.now(UTC) - ACTIVE_INTENT_FRESHNESS_WINDOW]
        if proposed_intent_id:
            exclude_clause = "AND pi.paper_intent_id <> %s"
            params.append(proposed_intent_id)
        session_clause = "AND (%s::text IS NULL OR pi.paper_session_id = %s::text)" if _column_exists(conn, "paper_intents", "paper_session_id") else "AND %s::text IS NULL AND %s::text IS NULL"
        return _fetchall(
            conn,
            f"""
            SELECT paper_intent_id, eligibility_id, market_id, side, intent_status, coordinator_decision_id, created_at, updated_at,
                   'HISTORICAL_ONLY' AS freshness_status
            FROM paper_intents pi
            WHERE pi.market_id = %s
              AND pi.intent_status = ANY(%s)
              AND pi.intent_type = 'PAPER_ENTRY_INTENT'
              AND pi.paper_only = true
              AND pi.live = false
              AND COALESCE(pi.is_dry_run_generated, false) = false
              AND COALESCE(pi.updated_at, pi.created_at) < %s
              {session_clause}
              {exclude_clause}
              AND NOT EXISTS (SELECT 1 FROM paper_fills pf WHERE pf.source_intent_id = pi.paper_intent_id)
              AND NOT EXISTS (SELECT 1 FROM paper_positions pp WHERE pp.payload_json->>'source_intent_id' = pi.paper_intent_id)
              AND NOT EXISTS (SELECT 1 FROM paper_orders po WHERE po.payload_json->>'source_intent_id' = pi.paper_intent_id)
            ORDER BY pi.created_at DESC, pi.id DESC
            """,
            tuple([*params[:3], paper_session_id, paper_session_id, *params[3:]]),
        )

    def _recent_opposite_closes(self, conn: Any, *, market_id: str, opposite_side: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_position_closes"):
            return []
        correlation_id = metadata.get("correlation_id")
        if correlation_id:
            return _fetchall(
                conn,
                """
                SELECT close_id, position_id::text AS position_id, market_id, side, exit_reason, created_at, correlation_id
                FROM paper_position_closes
                WHERE market_id = %s
                  AND side = %s
                  AND correlation_id = %s
                ORDER BY created_at DESC, id DESC
                """,
                (market_id, opposite_side, str(correlation_id)),
            )
        return _fetchall(
            conn,
            """
            SELECT close_id, position_id::text AS position_id, market_id, side, exit_reason, created_at, correlation_id
            FROM paper_position_closes
            WHERE market_id = %s
              AND side = %s
              AND created_at >= %s
              AND correlation_id IS NOT NULL
            ORDER BY created_at DESC, id DESC
            """,
            (market_id, opposite_side, datetime.now(UTC) - RECENT_CLOSE_WINDOW),
        )

    def _source_backed_rationale(
        self,
        conn: Any,
        *,
        coordinator_decision_id: str | None,
        evidence: dict[str, Any],
        metadata: dict[str, Any],
    ) -> tuple[str | None, str | None, bool]:
        candidates = []
        for payload in (metadata, evidence, _dict(evidence.get("source_evidence"))):
            rationale = _upper(payload.get("same_market_rationale_type") or payload.get("strategic_rationale_type") or payload.get("rationale_type"))
            source = payload.get("rationale_source") or payload.get("rationale_source_table")
            source_id = payload.get("rationale_source_id") or coordinator_decision_id
            if rationale:
                candidates.append((rationale, source, source_id))
        if coordinator_decision_id and _table_exists(conn, "mesh_coordinator_decisions"):
            row = _fetchone(conn, "SELECT * FROM mesh_coordinator_decisions WHERE decision_id = %s", (coordinator_decision_id,))
            if row:
                text = " ".join(str(row.get(key) or "") for key in ("decision_reason", "final_action", "final_stance")).upper()
                for rationale in ALLOWED_RATIONALES:
                    if rationale in text:
                        candidates.append((rationale, "mesh_coordinator_decisions", coordinator_decision_id))
        for rationale, source, source_id in candidates:
            if rationale not in ALLOWED_RATIONALES:
                return rationale, str(source or ""), False
            if self._source_exists(conn, str(source or ""), str(source_id or "")):
                return rationale, f"{source}:{source_id}", True
        return None, None, False

    def _source_exists(self, conn: Any, source: str, source_id: str) -> bool:
        if not source or not source_id:
            return False
        allowed = {
            "mesh_coordinator_decisions": ("decision_id",),
            "position_thesis_profiles": ("thesis_id", "profile_id"),
            "paper_eligibility_candidates": ("eligibility_id",),
            "paper_intents": ("paper_intent_id",),
        }
        if source not in allowed or not _table_exists(conn, source):
            return False
        for column in allowed[source]:
            if _column_exists(conn, source, column):
                row = _fetchone(conn, f"SELECT 1 FROM {source} WHERE {column} = %s LIMIT 1", (source_id,))
                if row:
                    return True
        return False

    def _build_decision(
        self,
        conn: Any,
        *,
        market_id: str,
        proposed_side: str,
        proposed_candidate_id: str | None,
        proposed_intent_id: str | None,
        existing_exposure: dict[str, Any],
        rationale: tuple[str | None, str | None, bool],
        decision: str,
        blocker_reason: str | None,
        dry_run: bool,
        metadata: dict[str, Any] | None,
        write_decision: bool,
    ) -> SameMarketSideGuardDecision:
        rationale_type, rationale_source, source_backed = rationale
        item = SameMarketSideGuardDecision(
            decision_id=f"same_market_guard_{uuid4().hex}",
            market_id=market_id,
            proposed_side=proposed_side,
            proposed_candidate_id=proposed_candidate_id,
            proposed_intent_id=proposed_intent_id,
            existing_exposure=existing_exposure,
            existing_open_positions_count=len(existing_exposure.get("open_positions", [])),
            existing_opposite_positions_count=len(existing_exposure.get("opposite_open_positions", [])),
            existing_same_side_positions_count=len(existing_exposure.get("same_side_open_positions", [])),
            existing_opposite_intents_count=len(existing_exposure.get("opposite_active_intents", [])),
            existing_same_side_intents_count=len(existing_exposure.get("same_side_active_intents", [])),
            recent_opposite_closes_count=len(existing_exposure.get("recent_opposite_closes", [])),
            batch_opposite_candidates_count=len(existing_exposure.get("batch_opposite_candidates", [])),
            rationale_type=rationale_type,
            rationale_source=rationale_source,
            source_backed=source_backed,
            decision=decision,
            blocker_reason=blocker_reason,
            dry_run=dry_run,
        )
        if write_decision and _table_exists(conn, "same_market_side_guard_decisions"):
            conn.execute(
                """
                INSERT INTO same_market_side_guard_decisions (
                    decision_id, market_id, proposed_side, proposed_candidate_id,
                    proposed_intent_id, existing_exposure_json, existing_open_positions_count,
                    existing_opposite_positions_count, existing_same_side_positions_count,
                    existing_opposite_intents_count, existing_same_side_intents_count,
                    recent_opposite_closes_count, batch_opposite_candidates_count,
                    rationale_type, rationale_source, source_backed, decision,
                    blocker_reason, dry_run, metadata_json
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (decision_id) DO NOTHING
                """,
                (
                    item.decision_id,
                    item.market_id,
                    item.proposed_side,
                    item.proposed_candidate_id,
                    item.proposed_intent_id,
                    Jsonb(_json_safe(item.existing_exposure)),
                    item.existing_open_positions_count,
                    item.existing_opposite_positions_count,
                    item.existing_same_side_positions_count,
                    item.existing_opposite_intents_count,
                    item.existing_same_side_intents_count,
                    item.recent_opposite_closes_count,
                    item.batch_opposite_candidates_count,
                    item.rationale_type,
                    item.rationale_source,
                    item.source_backed,
                    item.decision,
                    item.blocker_reason,
                    item.dry_run,
                    Jsonb(_json_safe(metadata or {})),
                ),
            )
        return item

    def _markets_with_both_sides(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_positions"):
            return []
        return _fetchall(
            conn,
            """
            SELECT market_id,
                   array_agg(DISTINCT intended_outcome ORDER BY intended_outcome) AS sides,
                   COUNT(*) AS positions,
                   COUNT(*) FILTER (WHERE current_status = 'OPEN' AND closed_at IS NULL) AS open_positions
            FROM paper_positions
            WHERE COALESCE(excluded_from_active_paper_truth, false) = false
            GROUP BY market_id
            HAVING COUNT(DISTINCT intended_outcome) > 1
            ORDER BY open_positions DESC, market_id ASC
            LIMIT %s
            """,
            (limit,),
        )

    def _sample_traces(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        markets = self._markets_with_both_sides(conn, limit=limit)
        traces = []
        for market in markets:
            market_id = str(market.get("market_id"))
            traces.append(
                {
                    "market_id": market_id,
                    "sides": market.get("sides"),
                    "positions": _fetchall(
                        conn,
                        """
                        SELECT id::text AS paper_position_id, intended_outcome AS side,
                               current_status, opened_at, closed_at, payload_json
                        FROM paper_positions
                        WHERE market_id = %s
                        ORDER BY opened_at ASC NULLS LAST, id ASC
                        """,
                        (market_id,),
                    ),
                    "latest_guard_decisions": _fetchall(
                        conn,
                        """
                        SELECT decision_id, proposed_side, decision, blocker_reason,
                               rationale_type, rationale_source, created_at
                        FROM same_market_side_guard_decisions
                        WHERE market_id = %s
                        ORDER BY created_at DESC, id DESC
                        LIMIT 5
                        """,
                        (market_id,),
                    ) if _table_exists(conn, "same_market_side_guard_decisions") else [],
                }
            )
        return traces


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = ANY(current_schemas(false))
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return bool(row)


def _upper(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip().upper()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _empty_dashboard(status: str = "OK") -> dict[str, Any]:
    return {
        "mock_data": False,
        "guard_status": status,
        "total_guard_decisions": 0,
        "blocked_count": 0,
        "review_count": 0,
        "allowed_count": 0,
        "opposing_side_blocks": 0,
        "duplicate_exposure_reviews": 0,
        "markets_with_both_sides": [],
        "latest_decisions": [],
        "sample_same_market_traces": [],
        "security_governance_status": SECURITY_GOVERNANCE_STATUS,
        "last_updated": datetime.now(UTC).isoformat(),
    }
