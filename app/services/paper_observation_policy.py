from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory


OBSERVATION_POLICY_ELIGIBLE = "OBSERVATION_POLICY_ELIGIBLE"
OBSERVATION_POLICY_WATCH = "OBSERVATION_POLICY_WATCH"
OBSERVATION_POLICY_BLOCKED = "OBSERVATION_POLICY_BLOCKED"
OBSERVATION_POLICY_INCOMPLETE = "OBSERVATION_POLICY_INCOMPLETE"

PAPER_OBSERVATION_BAND = "PAPER_OBSERVATION"
FULL_PAPER_BAND = "FULL_PAPER_CERTIFICATION"

OBSERVATION_SCORE_THRESHOLD = 60.0
DEFAULT_MAX_OBSERVATION_NOTIONAL = 5.0
DEFAULT_MAX_OPEN_POSITIONS = 1
DEFAULT_MAX_PER_MARKET = 1
DEFAULT_MAX_PER_TRIGGER_FAMILY = 1
DEFAULT_MAX_DAILY_ENTRIES = 3
DEFAULT_TIME_STOP_SECONDS = 24 * 60 * 60

EDGE_SUPPORTED_STATES = {"EDGE_SUPPORTED"}
THESIS_SUPPORTED_STATES = {"THESIS_SUPPORTED", "VALID"}
THESIS_WATCH_STATES = {"THESIS_WATCH", "WATCH"}
RISK_BLOCK_STATES = {"RISK_BLOCKED", "RISK_BLOCK", "RISK_DENIED"}
CAPITAL_BLOCK_STATES = {"CAPITAL_BLOCK", "CAPITAL_BLOCKED", "CAPITAL_DENIED"}
EXIT_READY_STATES = {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}
LIFECYCLE_BLOCK_STATES = {"BLOCKED", "DENIED", "LIFECYCLE_DENIED", "HARD_BLOCKED"}
FRESH_ORDERBOOK_STATES = {"FRESH", "ORDERBOOK_FRESH"}
TOKEN_VERIFIED_STATES = {"TOKENS_VERIFIED", "TOKEN_SIDE_DIRECT", "SIDE_DIRECTIONAL_YES", "SIDE_DIRECTIONAL_NO"}
VALID_SCOPE_STATES = {"CANDIDATE_SCOPED", "CANDIDATE_ACTIONABLE", "CANDIDATE_TARGETED_REFRESH"}


class PaperObservationPolicyReviewService:
    """DATA_ONLY policy review for learning-only Paper Observation classifications."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def refresh(self, *, limit: int = 500, force: bool = False) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"paper_observation_policy_{uuid4().hex}"
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "review_run_id": run_id, "classifications_reviewed": 0}
        limit = max(1, min(int(limit or 500), 2000))
        with self._factory.connect() as conn, conn.transaction():
            self._ensure_tables(conn)
            before = _safety_counts(conn)
            rows = self._paper_observation_rows(conn, limit=limit, force=force)
            stats = Counter()
            errors: list[str] = []
            for row in rows:
                try:
                    review = build_policy_review(row, review_run_id=run_id)
                    self._upsert_review(conn, review)
                    stats["classifications_reviewed"] += 1
                    state = review["observation_policy_state"]
                    stats["eligible_count"] += int(state == OBSERVATION_POLICY_ELIGIBLE)
                    stats["watch_count"] += int(state == OBSERVATION_POLICY_WATCH)
                    stats["blocked_count"] += int(state == OBSERVATION_POLICY_BLOCKED)
                    stats["incomplete_count"] += int(state == OBSERVATION_POLICY_INCOMPLETE)
                    stats["full_paper_ready_count"] += int(bool(row.get("full_paper_ready")))
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
            after = _safety_counts(conn)
            completed_at = datetime.now(UTC)
            status = "OK" if not errors else "PARTIAL" if stats["classifications_reviewed"] else "ERROR"
            self._insert_run(
                conn,
                review_run_id=run_id,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                latest_error=errors[0] if errors else None,
                metadata={
                    "limit": limit,
                    "force": force,
                    "data_only": True,
                    "observation_policy_review_only": True,
                    "execution_allowed": False,
                    "paper_allowed": False,
                    "shadow_allowed": False,
                    "live_allowed": False,
                    "safety_before": before,
                    "safety_after": after,
                    "trading_mutation": _trading_mutation(before, after),
                    "errors": errors[:5],
                },
                **stats,
            )
        return {
            "status": status,
            "review_run_id": run_id,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            **stats,
            "errors": errors[:5],
        }

    def summary(self, *, limit: int = 10) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return _empty_summary("DATABASE_UNAVAILABLE", now)
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            counts = self._counts(conn)
            latest = self._latest_run(conn)
            eligible = self._sample(conn, "observation_policy_state='OBSERVATION_POLICY_ELIGIBLE'", limit=limit)
            watch = self._sample(conn, "observation_policy_state='OBSERVATION_POLICY_WATCH'", limit=limit)
            blocked = self._sample(conn, "observation_policy_state='OBSERVATION_POLICY_BLOCKED'", limit=limit)
        return {
            "status": "REAL" if counts["total_paper_observation_classifications_reviewed"] else "MISSING",
            "source": "paper_observation_policy_reviews + proactive_seed_mesh_results",
            "last_updated": (latest or {}).get("completed_at") or now.isoformat(),
            "freshness_state": "FRESH" if latest else "MISSING",
            "readiness_state": "READY" if counts["observation_policy_eligible_count"] else "PARTIAL",
            "truth_state": "ACTIVE_FRESH" if counts["total_paper_observation_classifications_reviewed"] else "UNKNOWN",
            "counts": counts,
            "default_observation_limits": default_observation_limits(),
            "observation_policy_thresholds": observation_policy_thresholds(),
            "ledger_separation_readiness": ledger_separation_readiness(),
            "latest_review_run": latest,
            "latest_review_run_status": (latest or {}).get("status"),
            "latest_error": (latest or {}).get("latest_error"),
            "top_eligible_observation_candidates": eligible,
            "top_watch_candidates": watch,
            "top_blocked_candidates": blocked,
            "warnings": ["Paper Observation execution mode is not implemented; policy review is classification only."],
            "errors": [],
            "generated_at": now.isoformat(),
        }

    def by_seed(self, *, proactive_candidate_seed_id: str, limit: int = 20) -> dict[str, Any]:
        return self._by_field("proactive_candidate_seed_id", proactive_candidate_seed_id, limit=limit)

    def by_market(self, *, market_id: str, limit: int = 20) -> dict[str, Any]:
        return self._by_field("market_id", market_id, limit=limit)

    def fields_for_seed(self, *, proactive_candidate_seed_id: str | None) -> dict[str, Any]:
        if not proactive_candidate_seed_id or not self._factory.enabled:
            return _empty_policy_fields()
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                """
                SELECT *
                FROM paper_observation_policy_reviews
                WHERE proactive_candidate_seed_id=%s
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (proactive_candidate_seed_id,),
            ).fetchone()
        return _policy_fields(dict(row)) if row else _empty_policy_fields()

    def fields_for_market(self, *, market_id: str | None) -> dict[str, Any]:
        if not market_id or not self._factory.enabled:
            return {
                "paper_observation_policy_review_count": 0,
                "paper_observation_policy_eligible_count": 0,
                "paper_observation_policy_watch_count": 0,
                "paper_observation_policy_blocked_count": 0,
            }
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS review_count,
                    COUNT(*) FILTER (WHERE observation_policy_state='OBSERVATION_POLICY_ELIGIBLE') AS eligible_count,
                    COUNT(*) FILTER (WHERE observation_policy_state='OBSERVATION_POLICY_WATCH') AS watch_count,
                    COUNT(*) FILTER (WHERE observation_policy_state='OBSERVATION_POLICY_BLOCKED') AS blocked_count,
                    (ARRAY_AGG(paper_observation_policy_review_id ORDER BY updated_at DESC, id DESC))[1] AS latest_review_id,
                    (ARRAY_AGG(observation_policy_state ORDER BY updated_at DESC, id DESC))[1] AS latest_state
                FROM paper_observation_policy_reviews
                WHERE market_id=%s
                """,
                (market_id,),
            ).fetchone()
        item = dict(row or {})
        return {
            "paper_observation_policy_review_count": int(item.get("review_count") or 0),
            "paper_observation_policy_eligible_count": int(item.get("eligible_count") or 0),
            "paper_observation_policy_watch_count": int(item.get("watch_count") or 0),
            "paper_observation_policy_blocked_count": int(item.get("blocked_count") or 0),
            "latest_observation_policy_review_id": item.get("latest_review_id"),
            "latest_observation_policy_state": item.get("latest_state"),
        }

    def _paper_observation_rows(self, conn: Any, *, limit: int, force: bool) -> list[dict[str, Any]]:
        if not _table_exists(conn, "proactive_seed_mesh_results") or not _table_exists(conn, "proactive_candidate_seeds"):
            return []
        recent_filter = "" if force else """
            AND NOT EXISTS (
                SELECT 1
                FROM paper_observation_policy_reviews popr
                WHERE popr.proactive_candidate_seed_id=psr.proactive_candidate_seed_id
                  AND popr.seed_mesh_inquiry_id=psr.seed_mesh_inquiry_id
                  AND popr.updated_at >= now() - interval '24 hours'
            )
        """
        market_join = """
            LEFT JOIN market_universe_memory mum ON mum.market_memory_id=pcs.market_memory_id OR mum.market_id=pcs.market_id
        """ if _table_exists(conn, "market_universe_memory") else """
            LEFT JOIN LATERAL (
                SELECT NULL::text AS status, NULL::boolean AS active, NULL::text AS token_verification_state,
                       NULL::text AS identity_verification_state
            ) mum ON true
        """
        rows = conn.execute(
            f"""
            SELECT
                psr.*, psi.market_id AS inquiry_market_id, psi.condition_id AS inquiry_condition_id,
                psi.side AS inquiry_side, psi.token_id AS inquiry_token_id, psi.research_only AS inquiry_research_only,
                psi.execution_allowed AS inquiry_execution_allowed, psi.paper_allowed AS inquiry_paper_allowed,
                psi.shadow_allowed AS inquiry_shadow_allowed, psi.live_allowed AS inquiry_live_allowed,
                pcs.market_id AS seed_market_id, pcs.condition_id AS seed_condition_id, pcs.side AS seed_side,
                pcs.token_id AS seed_token_id, pcs.research_only AS seed_research_only,
                pcs.execution_allowed AS seed_execution_allowed, pcs.paper_allowed AS seed_paper_allowed,
                pcs.shadow_allowed AS seed_shadow_allowed, pcs.live_allowed AS seed_live_allowed,
                pcs.orderbook_refresh_state, pcs.token_side_resolution_state, pcs.candidate_event_scope_state,
                pcs.seed_state, pcs.seed_type, pcs.source_event_id, pcs.multi_trigger_id, pcs.trigger_type,
                pcs.targeted_revalidation_id, pcs.event_to_market_link_id, pcs.market_memory_id,
                pap.adapter_payload_id,
                mum.status AS market_memory_status, mum.active AS market_active,
                mum.token_verification_state AS market_token_verification_state,
                mum.identity_verification_state AS market_identity_verification_state
            FROM proactive_seed_mesh_results psr
            LEFT JOIN proactive_seed_mesh_inquiries psi ON psi.seed_mesh_inquiry_id=psr.seed_mesh_inquiry_id
            LEFT JOIN proactive_candidate_seeds pcs ON pcs.proactive_candidate_seed_id=psr.proactive_candidate_seed_id
            LEFT JOIN proactive_seed_mesh_adapter_payloads pap ON pap.seed_mesh_inquiry_id=psr.seed_mesh_inquiry_id
            {market_join}
            WHERE (
                psr.opportunity_decision_band='PAPER_OBSERVATION'
                OR psr.edge_state='EDGE_SUPPORTED'
                OR psr.opportunity_score IS NOT NULL
            )
            {recent_filter}
            ORDER BY
                CASE psr.opportunity_decision_band WHEN 'PAPER_OBSERVATION' THEN 0 ELSE 1 END,
                psr.opportunity_score DESC NULLS LAST,
                psr.updated_at DESC,
                psr.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _upsert_review(self, conn: Any, review: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO paper_observation_policy_reviews (
                paper_observation_policy_review_id, review_run_id, source_type,
                proactive_candidate_seed_id, seed_mesh_inquiry_id, adapter_payload_id, opportunity_score_id,
                market_id, condition_id, side, token_id, observation_policy_state, decision_band,
                opportunity_score, edge_state, thesis_state, risk_state, capital_state, exit_state,
                lifecycle_state, orderbook_state, token_verification_state, candidate_event_scope_state,
                lineage_state, observation_allowed_by_policy, data_only, observation_policy_review_only,
                execution_allowed, paper_allowed, shadow_allowed, live_allowed, max_observation_notional,
                max_open_positions, max_observations_per_market, max_observations_per_trigger_family,
                max_daily_observation_entries, time_stop_seconds, exit_required, invalidation_required,
                hard_blockers_json, soft_blockers_json, policy_blockers_json, required_to_pass_json,
                lineage_json, limits_json, metadata_json, policy_reason
            ) VALUES (
                %(paper_observation_policy_review_id)s, %(review_run_id)s, %(source_type)s,
                %(proactive_candidate_seed_id)s, %(seed_mesh_inquiry_id)s, %(adapter_payload_id)s, %(opportunity_score_id)s,
                %(market_id)s, %(condition_id)s, %(side)s, %(token_id)s, %(observation_policy_state)s, %(decision_band)s,
                %(opportunity_score)s, %(edge_state)s, %(thesis_state)s, %(risk_state)s, %(capital_state)s, %(exit_state)s,
                %(lifecycle_state)s, %(orderbook_state)s, %(token_verification_state)s, %(candidate_event_scope_state)s,
                %(lineage_state)s, %(observation_allowed_by_policy)s, %(data_only)s, %(observation_policy_review_only)s,
                %(execution_allowed)s, %(paper_allowed)s, %(shadow_allowed)s, %(live_allowed)s, %(max_observation_notional)s,
                %(max_open_positions)s, %(max_observations_per_market)s, %(max_observations_per_trigger_family)s,
                %(max_daily_observation_entries)s, %(time_stop_seconds)s, %(exit_required)s, %(invalidation_required)s,
                %(hard_blockers_json)s, %(soft_blockers_json)s, %(policy_blockers_json)s, %(required_to_pass_json)s,
                %(lineage_json)s, %(limits_json)s, %(metadata_json)s, %(policy_reason)s
            )
            ON CONFLICT (paper_observation_policy_review_id) DO UPDATE SET
                review_run_id=EXCLUDED.review_run_id,
                observation_policy_state=EXCLUDED.observation_policy_state,
                observation_allowed_by_policy=EXCLUDED.observation_allowed_by_policy,
                hard_blockers_json=EXCLUDED.hard_blockers_json,
                soft_blockers_json=EXCLUDED.soft_blockers_json,
                policy_blockers_json=EXCLUDED.policy_blockers_json,
                required_to_pass_json=EXCLUDED.required_to_pass_json,
                lineage_json=EXCLUDED.lineage_json,
                limits_json=EXCLUDED.limits_json,
                metadata_json=EXCLUDED.metadata_json,
                policy_reason=EXCLUDED.policy_reason,
                updated_at=now()
            """,
            _sql_params(review),
        )

    def _insert_run(self, conn: Any, *, review_run_id: str, status: str, started_at: datetime, completed_at: datetime, latest_error: str | None, metadata: dict[str, Any], **stats: Any) -> None:
        conn.execute(
            """
            INSERT INTO paper_observation_policy_review_runs (
                review_run_id, status, started_at, completed_at, classifications_reviewed,
                eligible_count, watch_count, blocked_count, incomplete_count, full_paper_ready_count,
                latest_error, metadata_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (review_run_id) DO UPDATE SET
                status=EXCLUDED.status,
                completed_at=EXCLUDED.completed_at,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            (
                review_run_id,
                status,
                started_at,
                completed_at,
                int(stats.get("classifications_reviewed") or 0),
                int(stats.get("eligible_count") or 0),
                int(stats.get("watch_count") or 0),
                int(stats.get("blocked_count") or 0),
                int(stats.get("incomplete_count") or 0),
                int(stats.get("full_paper_ready_count") or 0),
                latest_error,
                Jsonb(_jsonable(metadata)),
            ),
        )

    def _counts(self, conn: Any) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE observation_policy_state='OBSERVATION_POLICY_ELIGIBLE') AS eligible,
                COUNT(*) FILTER (WHERE observation_policy_state='OBSERVATION_POLICY_WATCH') AS watch,
                COUNT(*) FILTER (WHERE observation_policy_state='OBSERVATION_POLICY_BLOCKED') AS blocked,
                COUNT(*) FILTER (WHERE observation_policy_state='OBSERVATION_POLICY_INCOMPLETE') AS incomplete,
                COUNT(*) FILTER (WHERE decision_band='FULL_PAPER_CERTIFICATION') AS full_paper_ready,
                AVG(opportunity_score) AS avg_score
            FROM paper_observation_policy_reviews
            """
        ).fetchone()
        base = dict(row or {})
        out = {
            "total_paper_observation_classifications_reviewed": int(base.get("total") or 0),
            "observation_policy_eligible_count": int(base.get("eligible") or 0),
            "observation_policy_watch_count": int(base.get("watch") or 0),
            "observation_policy_blocked_count": int(base.get("blocked") or 0),
            "observation_policy_incomplete_count": int(base.get("incomplete") or 0),
            "full_paper_ready_count": int(base.get("full_paper_ready") or 0),
            "average_opportunity_score": round(float(base.get("avg_score") or 0.0), 2),
        }
        for field, key in (
            ("risk_state", "risk_state_counts"),
            ("capital_state", "capital_state_counts"),
            ("exit_state", "exit_state_counts"),
            ("lifecycle_state", "lifecycle_state_counts"),
            ("edge_state", "edge_state_counts"),
            ("thesis_state", "thesis_state_counts"),
            ("observation_policy_state", "policy_state_counts"),
        ):
            rows = conn.execute(f"SELECT {field}, COUNT(*) AS count FROM paper_observation_policy_reviews GROUP BY {field} ORDER BY count DESC").fetchall()
            out[key] = {str(item[field]): int(item["count"] or 0) for item in rows}
        out["hard_blocker_counts"] = _json_array_counts(conn, "hard_blockers_json")
        out["soft_blocker_counts"] = _json_array_counts(conn, "soft_blockers_json")
        out["policy_blocker_counts"] = _json_array_counts(conn, "policy_blockers_json")
        return out

    def _sample(self, conn: Any, where: str, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"""
            SELECT *
            FROM paper_observation_policy_reviews
            WHERE {where}
            ORDER BY opportunity_score DESC, updated_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _by_field(self, field: str, value: str, *, limit: int) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "results": []}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            rows = conn.execute(
                f"SELECT * FROM paper_observation_policy_reviews WHERE {field}=%s ORDER BY updated_at DESC, id DESC LIMIT %s",
                (value, limit),
            ).fetchall()
        return {"status": "REAL" if rows else "MISSING", "results": [_jsonable(dict(row)) for row in rows]}

    def _latest_run(self, conn: Any) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM paper_observation_policy_review_runs ORDER BY completed_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
        return _jsonable(dict(row)) if row else None

    def _ensure_tables(self, conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_observation_policy_reviews (
                id BIGSERIAL PRIMARY KEY,
                paper_observation_policy_review_id TEXT NOT NULL UNIQUE,
                review_run_id TEXT,
                source_type TEXT NOT NULL DEFAULT 'PROACTIVE_SEED_MESH',
                proactive_candidate_seed_id TEXT,
                seed_mesh_inquiry_id TEXT,
                adapter_payload_id TEXT,
                opportunity_score_id TEXT,
                market_id TEXT,
                condition_id TEXT,
                side TEXT,
                token_id TEXT,
                observation_policy_state TEXT NOT NULL,
                decision_band TEXT NOT NULL DEFAULT 'PAPER_OBSERVATION',
                opportunity_score NUMERIC NOT NULL DEFAULT 0,
                edge_state TEXT,
                thesis_state TEXT,
                risk_state TEXT,
                capital_state TEXT,
                exit_state TEXT,
                lifecycle_state TEXT,
                orderbook_state TEXT,
                token_verification_state TEXT,
                candidate_event_scope_state TEXT,
                lineage_state TEXT NOT NULL DEFAULT 'MISSING',
                observation_allowed_by_policy BOOLEAN NOT NULL DEFAULT FALSE,
                data_only BOOLEAN NOT NULL DEFAULT TRUE,
                observation_policy_review_only BOOLEAN NOT NULL DEFAULT TRUE,
                execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                paper_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                shadow_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                live_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                max_observation_notional NUMERIC NOT NULL DEFAULT 0,
                max_open_positions INTEGER NOT NULL DEFAULT 0,
                max_observations_per_market INTEGER NOT NULL DEFAULT 1,
                max_observations_per_trigger_family INTEGER NOT NULL DEFAULT 1,
                max_daily_observation_entries INTEGER NOT NULL DEFAULT 1,
                time_stop_seconds INTEGER,
                exit_required BOOLEAN NOT NULL DEFAULT TRUE,
                invalidation_required BOOLEAN NOT NULL DEFAULT TRUE,
                hard_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                soft_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                policy_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                lineage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                limits_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                policy_reason TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_observation_policy_review_runs (
                id BIGSERIAL PRIMARY KEY,
                review_run_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                classifications_reviewed INTEGER NOT NULL DEFAULT 0,
                eligible_count INTEGER NOT NULL DEFAULT 0,
                watch_count INTEGER NOT NULL DEFAULT 0,
                blocked_count INTEGER NOT NULL DEFAULT 0,
                incomplete_count INTEGER NOT NULL DEFAULT 0,
                full_paper_ready_count INTEGER NOT NULL DEFAULT 0,
                latest_error TEXT,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def build_policy_review(row: dict[str, Any], *, review_run_id: str = "test") -> dict[str, Any]:
    hard = _list(row.get("hard_blockers_json"))
    soft = _list(row.get("soft_blockers_json"))
    policy_blockers: list[str] = []
    required: list[str] = []

    score = _float(row.get("opportunity_score"))
    decision_band = str(row.get("opportunity_decision_band") or row.get("decision_band") or "UNKNOWN")
    edge_state = _upper(row.get("edge_state"))
    thesis_state = _upper(row.get("trade_thesis_state") or row.get("thesis_state"))
    risk_state = _upper(row.get("risk_state"))
    capital_state = _upper(row.get("capital_state"))
    exit_state = _upper(row.get("exit_state"))
    lifecycle_state = _upper(row.get("lifecycle_state"))
    orderbook_state = _upper(row.get("orderbook_refresh_state") or row.get("orderbook_state"))
    token_state = _upper(row.get("market_token_verification_state") or row.get("token_verification_state") or row.get("token_side_resolution_state"))
    scope_state = _upper(row.get("candidate_event_scope_state"))
    market_status = _upper(row.get("market_memory_status"))
    market_active = bool(row.get("market_active")) if row.get("market_active") is not None else market_status in {"", "ACTIVE"}

    lineage = {
        "source_event_id": row.get("source_event_id"),
        "multi_trigger_id": row.get("multi_trigger_id"),
        "event_to_market_link_id": row.get("event_to_market_link_id"),
        "targeted_revalidation_id": row.get("targeted_revalidation_id"),
        "proactive_candidate_seed_id": row.get("proactive_candidate_seed_id"),
        "seed_mesh_inquiry_id": row.get("seed_mesh_inquiry_id"),
        "adapter_payload_id": row.get("adapter_payload_id"),
        "market_memory_id": row.get("market_memory_id"),
    }
    lineage_state = _lineage_state(lineage)

    if decision_band != PAPER_OBSERVATION_BAND:
        policy_blockers.append("decision_band_not_paper_observation")
    if edge_state not in EDGE_SUPPORTED_STATES:
        policy_blockers.append("edge_not_supported")
    if thesis_state in THESIS_WATCH_STATES:
        policy_blockers.append("thesis_watch_not_observation_policy_eligible")
    elif thesis_state not in THESIS_SUPPORTED_STATES:
        policy_blockers.append("thesis_not_supported")
    if score < OBSERVATION_SCORE_THRESHOLD:
        policy_blockers.append("opportunity_score_below_observation_threshold")
    if not market_active or market_status in {"CLOSED", "RESOLVED", "ARCHIVED"}:
        policy_blockers.append("market_not_active")
    if token_state not in TOKEN_VERIFIED_STATES:
        policy_blockers.append("token_side_not_verified")
    if orderbook_state not in FRESH_ORDERBOOK_STATES:
        policy_blockers.append("orderbook_not_fresh")
    if scope_state and scope_state not in VALID_SCOPE_STATES:
        policy_blockers.append("candidate_event_scope_not_candidate_scoped")
    if lineage_state != "COMPLETE":
        policy_blockers.append("lineage_not_complete")
    if risk_state in RISK_BLOCK_STATES:
        policy_blockers.append("risk_hard_blocked")
    if capital_state in CAPITAL_BLOCK_STATES:
        policy_blockers.append("capital_hard_blocked")
    if exit_state not in EXIT_READY_STATES:
        policy_blockers.append("exit_not_ready")
    if lifecycle_state in LIFECYCLE_BLOCK_STATES:
        policy_blockers.append("lifecycle_hard_blocked")
    if hard:
        policy_blockers.append("existing_hard_blockers_present")
    if any(bool(row.get(flag)) for flag in ("seed_execution_allowed", "seed_paper_allowed", "seed_shadow_allowed", "seed_live_allowed", "inquiry_execution_allowed", "inquiry_paper_allowed", "inquiry_shadow_allowed", "inquiry_live_allowed")):
        policy_blockers.append("unsafe_execution_or_mode_flag_true")

    required.extend(_required_to_pass(policy_blockers, soft))
    state = _policy_state(policy_blockers, soft)
    allowed = state == OBSERVATION_POLICY_ELIGIBLE
    limits = default_observation_limits()
    review_id = _review_id(row)
    return {
        "paper_observation_policy_review_id": review_id,
        "review_run_id": review_run_id,
        "source_type": "PROACTIVE_SEED_MESH",
        "proactive_candidate_seed_id": row.get("proactive_candidate_seed_id"),
        "seed_mesh_inquiry_id": row.get("seed_mesh_inquiry_id"),
        "adapter_payload_id": row.get("adapter_payload_id"),
        "opportunity_score_id": row.get("opportunity_score_id") or row.get("seed_mesh_result_id"),
        "market_id": row.get("seed_market_id") or row.get("market_id") or row.get("inquiry_market_id"),
        "condition_id": row.get("seed_condition_id") or row.get("condition_id") or row.get("inquiry_condition_id"),
        "side": row.get("seed_side") or row.get("side") or row.get("inquiry_side"),
        "token_id": row.get("seed_token_id") or row.get("token_id") or row.get("inquiry_token_id"),
        "observation_policy_state": state,
        "decision_band": decision_band,
        "opportunity_score": score,
        "edge_state": edge_state,
        "thesis_state": thesis_state,
        "risk_state": risk_state,
        "capital_state": capital_state,
        "exit_state": exit_state,
        "lifecycle_state": lifecycle_state,
        "orderbook_state": orderbook_state,
        "token_verification_state": token_state,
        "candidate_event_scope_state": scope_state,
        "lineage_state": lineage_state,
        "observation_allowed_by_policy": allowed,
        "data_only": True,
        "observation_policy_review_only": True,
        "execution_allowed": False,
        "paper_allowed": False,
        "shadow_allowed": False,
        "live_allowed": False,
        "max_observation_notional": limits["max_observation_notional"],
        "max_open_positions": limits["max_total_open_observation_positions"],
        "max_observations_per_market": limits["max_observation_positions_per_market"],
        "max_observations_per_trigger_family": limits["max_observation_positions_per_trigger_family"],
        "max_daily_observation_entries": limits["max_daily_observation_entries"],
        "time_stop_seconds": limits["time_stop_seconds"],
        "exit_required": True,
        "invalidation_required": True,
        "hard_blockers_json": hard,
        "soft_blockers_json": soft,
        "policy_blockers_json": _unique(policy_blockers),
        "required_to_pass_json": _unique(required),
        "lineage_json": lineage,
        "limits_json": limits,
        "metadata_json": {
            "not_full_paper": True,
            "not_shadow_ready": True,
            "not_live_ready": True,
            "observation_execution_mode_implemented": False,
            "paper_observation_classification_only": True,
            "full_paper_ready_from_mesh": bool(row.get("full_paper_ready")),
        },
        "policy_reason": _policy_reason(state, policy_blockers, soft),
    }


def observation_policy_thresholds() -> dict[str, Any]:
    return {
        "observation_score_threshold": OBSERVATION_SCORE_THRESHOLD,
        "edge_required": "EDGE_SUPPORTED",
        "thesis_supported_required_for_eligible": True,
        "thesis_watch_policy": "OBSERVATION_POLICY_WATCH",
        "risk_review_allowed_for_observation": True,
        "capital_watch_allowed_for_observation": True,
        "risk_blocked_blocks_observation": True,
        "capital_blocked_blocks_observation": True,
        "fresh_orderbook_required": True,
        "token_side_verified_required": True,
    }


def default_observation_limits() -> dict[str, Any]:
    return {
        "max_observation_notional": DEFAULT_MAX_OBSERVATION_NOTIONAL,
        "max_total_open_observation_positions": DEFAULT_MAX_OPEN_POSITIONS,
        "max_observation_positions_per_market": DEFAULT_MAX_PER_MARKET,
        "max_observation_positions_per_trigger_family": DEFAULT_MAX_PER_TRIGGER_FAMILY,
        "max_daily_observation_entries": DEFAULT_MAX_DAILY_ENTRIES,
        "time_stop_seconds": DEFAULT_TIME_STOP_SECONDS,
        "exit_required": True,
        "invalidation_required": True,
        "no_averaging_down": True,
        "no_pyramiding": True,
        "excluded_from_full_paper_certification": True,
        "excluded_from_shadow_readiness": True,
        "excluded_from_live_readiness": True,
    }


def ledger_separation_readiness() -> dict[str, Any]:
    return {
        "ready_for_observation_execution": False,
        "paper_ledger_has_observation_mode_columns": False,
        "paper_ledger_has_observation_policy_review_id": False,
        "paper_ledger_has_certification_exclusion_flags": False,
        "recommendation": "Future Stage 8 should add observation-only ledger tags before any observation execution mode.",
    }


def _policy_state(policy_blockers: list[str], soft: list[str]) -> str:
    blocker_set = set(policy_blockers)
    incomplete = {"lineage_not_complete", "thesis_not_supported", "exit_not_ready"}
    watch_only = {
        "decision_band_not_paper_observation",
        "thesis_watch_not_observation_policy_eligible",
        "existing_hard_blockers_present",
    }
    hard_safety = {
        "edge_not_supported",
        "market_not_active",
        "token_side_not_verified",
        "orderbook_not_fresh",
        "candidate_event_scope_not_candidate_scoped",
        "risk_hard_blocked",
        "capital_hard_blocked",
        "lifecycle_hard_blocked",
        "unsafe_execution_or_mode_flag_true",
    }
    if blocker_set & incomplete:
        return OBSERVATION_POLICY_INCOMPLETE
    if blocker_set & hard_safety:
        return OBSERVATION_POLICY_BLOCKED
    if "thesis_watch_not_observation_policy_eligible" in blocker_set:
        return OBSERVATION_POLICY_WATCH
    if blocker_set - watch_only:
        return OBSERVATION_POLICY_BLOCKED
    if blocker_set & watch_only:
        return OBSERVATION_POLICY_WATCH
    return OBSERVATION_POLICY_ELIGIBLE


def _required_to_pass(policy_blockers: list[str], soft: list[str]) -> list[str]:
    mapping = {
        "decision_band_not_paper_observation": "Candidate must classify as PAPER_OBSERVATION before observation policy review.",
        "edge_not_supported": "Edge must be EDGE_SUPPORTED for observation eligibility.",
        "thesis_watch_not_observation_policy_eligible": "Trade thesis must move from watch to supported, or policy must explicitly allow thesis-watch observation.",
        "thesis_not_supported": "A supported trade thesis is required.",
        "opportunity_score_below_observation_threshold": "Opportunity score must be at least the configured observation threshold.",
        "market_not_active": "Market must be active and non-terminal.",
        "token_side_not_verified": "Token and side must be verified.",
        "orderbook_not_fresh": "Orderbook must be fresh.",
        "candidate_event_scope_not_candidate_scoped": "Candidate event scope must be candidate-scoped for observation eligibility.",
        "lineage_not_complete": "Source/trigger -> revalidation -> seed -> mesh adapter lineage must be complete.",
        "risk_hard_blocked": "Risk must not be hard blocked.",
        "capital_hard_blocked": "Capital must not be hard blocked.",
        "exit_not_ready": "Exit must be ready or observation time-stop/invalidation must be explicitly defined.",
        "lifecycle_hard_blocked": "Lifecycle must not be hard blocked.",
        "existing_hard_blockers_present": "Existing hard blockers must clear under current policy.",
        "unsafe_execution_or_mode_flag_true": "Research seed and inquiry execution/paper/shadow/live flags must remain false.",
    }
    required = [mapping[item] for item in policy_blockers if item in mapping]
    if "capital_watch_not_full_paper_ready" in soft:
        required.append("Capital WATCH is allowed for observation review only; CAPITAL_SUPPORT is still required for Full Paper.")
    if "risk_review_not_full_paper_ready" in soft:
        required.append("Risk REVIEW is allowed for observation review only; RISK_OK is still required for Full Paper.")
    if "reward_evidence_weak_or_missing" in soft:
        required.append("Improve explicit reward evidence before Full Paper certification.")
    return required


def _policy_reason(state: str, blockers: list[str], soft: list[str]) -> str:
    if state == OBSERVATION_POLICY_ELIGIBLE:
        return "PAPER_OBSERVATION classification passes review-only policy; execution remains disabled."
    if blockers:
        return f"{state}: {', '.join(_unique(blockers))}."
    if soft:
        return f"{state}: soft blockers remain for Full Paper: {', '.join(_unique(soft))}."
    return state


def _lineage_state(lineage: dict[str, Any]) -> str:
    required = ["targeted_revalidation_id", "proactive_candidate_seed_id", "seed_mesh_inquiry_id", "adapter_payload_id", "market_memory_id"]
    has_origin = bool(lineage.get("source_event_id") or lineage.get("multi_trigger_id"))
    if has_origin and all(lineage.get(key) for key in required):
        return "COMPLETE"
    if has_origin or any(lineage.get(key) for key in required):
        return "PARTIAL"
    return "MISSING"


def _review_id(row: dict[str, Any]) -> str:
    base = "|".join(str(row.get(key) or "") for key in ("seed_mesh_result_id", "seed_mesh_inquiry_id", "proactive_candidate_seed_id"))
    return "paper_observation_policy_" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


def _policy_fields(row: dict[str, Any]) -> dict[str, Any]:
    item = _jsonable(row)
    return {
        "paper_observation_policy_review_id": item.get("paper_observation_policy_review_id"),
        "paper_observation_policy_state": item.get("observation_policy_state"),
        "observation_policy_state": item.get("observation_policy_state"),
        "observation_allowed_by_policy": bool(item.get("observation_allowed_by_policy")),
        "observation_policy_blockers": item.get("policy_blockers_json") or [],
        "observation_policy_required_to_pass": item.get("required_to_pass_json") or [],
        "observation_policy_limits": item.get("limits_json") or default_observation_limits(),
        "observation_execution_mode_implemented": False,
        "observation_paper_intent_creation_allowed": False,
        "observation_policy_execution_allowed": False,
        "observation_policy_paper_allowed": False,
        "observation_policy_shadow_allowed": False,
        "observation_policy_live_allowed": False,
    }


def _empty_policy_fields() -> dict[str, Any]:
    return {
        "paper_observation_policy_review_id": None,
        "paper_observation_policy_state": "NOT_REVIEWED",
        "observation_policy_state": "NOT_REVIEWED",
        "observation_allowed_by_policy": False,
        "observation_policy_blockers": [],
        "observation_policy_required_to_pass": [],
        "observation_policy_limits": default_observation_limits(),
        "observation_execution_mode_implemented": False,
        "observation_paper_intent_creation_allowed": False,
        "observation_policy_execution_allowed": False,
        "observation_policy_paper_allowed": False,
        "observation_policy_shadow_allowed": False,
        "observation_policy_live_allowed": False,
    }


def _json_array_counts(conn: Any, column: str) -> dict[str, int]:
    rows = conn.execute(
        f"""
        SELECT value, COUNT(*) AS count
        FROM paper_observation_policy_reviews,
             LATERAL jsonb_array_elements_text({column}) AS value
        GROUP BY value
        ORDER BY count DESC, value
        """
    ).fetchall()
    return {str(row["value"]): int(row["count"] or 0) for row in rows}


def _safety_counts(conn: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "positions", "shadow_orders"):
        out[table] = 0
        if _table_exists(conn, table):
            out[table] = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
    return out


def _trading_mutation(before: dict[str, int], after: dict[str, int]) -> bool:
    return any(int(after.get(key, 0)) != int(before.get(key, 0)) for key in set(before) | set(after))


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _sql_params(review: dict[str, Any]) -> dict[str, Any]:
    out = dict(review)
    for key in ("hard_blockers_json", "soft_blockers_json", "policy_blockers_json", "required_to_pass_json", "lineage_json", "limits_json", "metadata_json"):
        out[key] = Jsonb(_jsonable(out.get(key)))
    return out


def _empty_summary(status: str, now: datetime) -> dict[str, Any]:
    return {
        "status": status,
        "source": "paper_observation_policy_reviews",
        "last_updated": now.isoformat(),
        "freshness_state": "MISSING",
        "readiness_state": "UNKNOWN",
        "truth_state": "UNKNOWN",
        "counts": {},
        "warnings": ["Database unavailable."],
        "errors": [],
        "generated_at": now.isoformat(),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__float__") and value.__class__.__name__ == "Decimal":
        return float(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)] if value else []


def _float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _upper(value: Any) -> str:
    return str(value or "").upper()


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
