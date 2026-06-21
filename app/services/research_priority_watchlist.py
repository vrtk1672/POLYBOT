from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.multi_trigger_candidate_generation import MultiTriggerProactiveCandidateGeneratorService
from app.services.proactive_seed_mesh_inquiry import ProactiveSeedMeshInquiryService


RECENT_WINDOW_HOURS = 72
DEFAULT_REFRESH_LIMIT = 500

CADENCE_BY_BAND = {
    "HIGH": 300,
    "MEDIUM": 900,
    "LOW": 3600,
    "DORMANT": 21600,
    "ARCHIVED": 0,
    "PRIORITY_UNKNOWN": 3600,
}


class ResearchPriorityWatchlistService:
    """DATA_ONLY market research priority and refresh cadence projection.

    Stage 4.5 computes market-level research focus from existing memory,
    recall, revalidation, seed, score, and actionability evidence. It records
    scheduler recommendations only; it never triggers trades, paper artifacts,
    live artifacts, or execution candidates.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def refresh(self, *, limit: int = DEFAULT_REFRESH_LIMIT, force: bool = False) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"research_priority_watchlist_{uuid4().hex}"
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "priority_run_id": run_id, "markets_seen": 0}
        limit = max(1, min(int(limit or DEFAULT_REFRESH_LIMIT), 2000))
        with self._factory.connect() as conn, conn.transaction():
            self._ensure_tables(conn)
            safety_before = _safety_counts(conn)
            rows = self._market_evidence_rows(conn, limit=limit)
            stats = {
                "markets_seen": 0,
                "markets_updated": 0,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
                "dormant_count": 0,
                "archived_count": 0,
                "due_now_count": 0,
            }
            errors: list[str] = []
            for row in rows:
                try:
                    profile = build_priority_profile(dict(row), run_id=run_id, now=started_at)
                    self._upsert_watchlist(conn, profile)
                    band = str(profile["priority_band"]).lower()
                    if band in {"high", "medium", "low", "dormant", "archived"}:
                        stats[f"{band}_count"] += 1
                    stats["due_now_count"] += int(profile["scheduler_state"] == "DUE")
                    stats["markets_seen"] += 1
                    stats["markets_updated"] += 1
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
            safety_after = _safety_counts(conn)
            completed_at = datetime.now(UTC)
            status = "OK" if not errors else "PARTIAL" if stats["markets_seen"] else "ERROR"
            self._insert_run(
                conn,
                priority_run_id=run_id,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                latest_error=errors[0] if errors else None,
                metadata={
                    "limit": limit,
                    "force": force,
                    "safety_before": safety_before,
                    "safety_after": safety_after,
                    "trading_mutation": _trading_mutation(safety_before, safety_after),
                    "paper_artifacts_created": False,
                    "execution_candidates_created": False,
                    "scheduler_behavior": "RECOMMENDATIONS_ONLY_NO_DEEP_REFRESH",
                    "errors": errors[:5],
                },
                **stats,
            )
        return {
            "status": status,
            "priority_run_id": run_id,
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
            high = self._sample(conn, "priority_band='HIGH'", limit=limit)
            medium = self._sample(conn, "priority_band='MEDIUM'", limit=limit)
            dormant = self._sample(conn, "priority_band='DORMANT'", limit=limit)
            archived = self._sample(conn, "priority_band='ARCHIVED'", limit=limit)
            due = self._due_rows(conn, limit=limit)
        return {
            "status": "REAL" if counts["total_watchlist_rows"] else "MISSING",
            "source": "research_priority_watchlist + market/source/revalidation/seed/score truth",
            "last_updated": (latest or {}).get("completed_at") or now.isoformat(),
            "freshness_state": "FRESH" if latest and counts["total_watchlist_rows"] else "MISSING",
            "readiness_state": "READY" if counts["total_watchlist_rows"] else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if counts["total_watchlist_rows"] else "UNKNOWN",
            "counts": counts,
            "latest_priority_refresh_run": latest,
            "top_high_priority_markets": high,
            "top_medium_priority_markets": medium,
            "dormant_markets_sample": dormant,
            "archived_markets_sample": archived,
            "next_refresh_due_samples": due,
            "priority_formula": priority_formula(),
            "refresh_cadence_policy": CADENCE_BY_BAND,
            "scheduler_behavior": "RECOMMENDATIONS_ONLY_NO_DEEP_REFRESH",
            "warnings": [] if counts["total_watchlist_rows"] else ["Research priority watchlist has not been refreshed yet."],
            "errors": [],
            "generated_at": now.isoformat(),
        }

    def by_market(self, *, market_id: str) -> dict[str, Any]:
        if not market_id:
            return {"status": "BLOCKED", "blocker": "MARKET_ID_REQUIRED", "watchlist": None}
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "watchlist": None}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                """
                SELECT *
                FROM research_priority_watchlist
                WHERE market_id=%s
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
        return {"status": "REAL" if row else "MISSING", "watchlist": _jsonable(dict(row)) if row else None}

    def due(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "due_markets": []}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            rows = self._due_rows(conn, limit=limit)
        grouped: dict[str, list[dict[str, Any]]] = {"HIGH": [], "MEDIUM": [], "LOW": [], "DORMANT": []}
        for row in rows:
            grouped.setdefault(str(row.get("priority_band") or "LOW"), []).append(row)
        return {"status": "REAL" if rows else "MISSING", "due_markets": rows, "by_priority": grouped}

    def fields_for_market(self, *, market_id: str | None) -> dict[str, Any]:
        if not market_id or not self._factory.enabled:
            return _empty_market_fields()
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                """
                SELECT research_watchlist_id, priority_band, priority_score,
                       refresh_cadence_seconds, next_refresh_due_at, scheduler_state,
                       priority_reasons_json, demotion_reasons_json
                FROM research_priority_watchlist
                WHERE market_id=%s
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
        if not row:
            return _empty_market_fields()
        item = dict(row)
        mesh_fields = ProactiveSeedMeshInquiryService(connection_factory=self._factory).fields_for_market(market_id=market_id)
        try:
            trigger_fields = MultiTriggerProactiveCandidateGeneratorService(connection_factory=self._factory).fields_for_market(market_id=market_id)
        except Exception as exc:
            trigger_fields = {"multi_trigger_error": f"{type(exc).__name__}: {exc}"}
        return {
            "research_watchlist_id": item.get("research_watchlist_id"),
            "research_priority_band": item.get("priority_band"),
            "research_priority_score": _float(item.get("priority_score")),
            "next_refresh_due_at": _iso(item.get("next_refresh_due_at")),
            "refresh_cadence_seconds": int(item.get("refresh_cadence_seconds") or 0),
            "watchlist_scheduler_state": item.get("scheduler_state"),
            "watchlist_reason": (item.get("priority_reasons_json") or [None])[0] if isinstance(item.get("priority_reasons_json"), list) else None,
            "priority_reasons": item.get("priority_reasons_json") or [],
            "demotion_reasons": item.get("demotion_reasons_json") or [],
            "mesh_inquiry_count": mesh_fields.get("seed_mesh_inquiry_count", 0),
            "mesh_completed_count": mesh_fields.get("mesh_completed_count", 0),
            "best_seed_opportunity_score": mesh_fields.get("seed_mesh_best_score"),
            "paper_observation_interest_from_seed_mesh": mesh_fields.get("paper_observation_interest_from_seed_mesh", 0),
            **trigger_fields,
        }

    def _market_evidence_rows(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "market_universe_memory"):
            return []
        event_join = """
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) FILTER (WHERE emr.link_type='DIRECT_LINK' AND emr.updated_at >= now() - interval '72 hours') AS recent_direct_event_count,
                    COUNT(*) FILTER (WHERE emr.link_type='LIKELY_LINK' AND emr.updated_at >= now() - interval '72 hours') AS recent_likely_event_count
                FROM event_to_market_recall emr
                WHERE emr.market_id=mum.market_id
            ) ev ON true
        """ if _table_exists(conn, "event_to_market_recall") else """
            LEFT JOIN LATERAL (SELECT 0::integer AS recent_direct_event_count, 0::integer AS recent_likely_event_count) ev ON true
        """
        reval_join = """
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) FILTER (WHERE updated_at >= now() - interval '72 hours') AS recent_revalidation_count,
                    (ARRAY_AGG(liquidity_state ORDER BY updated_at DESC, id DESC))[1] AS latest_liquidity_state,
                    (ARRAY_AGG(spread_state ORDER BY updated_at DESC, id DESC))[1] AS latest_spread_state,
                    (ARRAY_AGG(payout_odds_state ORDER BY updated_at DESC, id DESC))[1] AS latest_payout_odds_state,
                    (ARRAY_AGG(movement_state ORDER BY updated_at DESC, id DESC))[1] AS latest_movement_state
                FROM targeted_market_revalidations tmr
                WHERE tmr.market_id=mum.market_id
            ) rv ON true
        """ if _table_exists(conn, "targeted_market_revalidations") else """
            LEFT JOIN LATERAL (
                SELECT 0::integer AS recent_revalidation_count, NULL::text AS latest_liquidity_state,
                       NULL::text AS latest_spread_state, NULL::text AS latest_payout_odds_state,
                       NULL::text AS latest_movement_state
            ) rv ON true
        """
        seed_join = """
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) FILTER (WHERE updated_at >= now() - interval '72 hours') AS recent_candidate_seed_count,
                    COUNT(*) FILTER (WHERE side='YES' AND updated_at >= now() - interval '72 hours') AS recent_yes_seed_count,
                    COUNT(*) FILTER (WHERE side='NO' AND updated_at >= now() - interval '72 hours') AS recent_no_seed_count
                FROM proactive_candidate_seeds pcs
                WHERE pcs.market_id=mum.market_id
            ) sd ON true
        """ if _table_exists(conn, "proactive_candidate_seeds") else """
            LEFT JOIN LATERAL (
                SELECT 0::integer AS recent_candidate_seed_count, 0::integer AS recent_yes_seed_count, 0::integer AS recent_no_seed_count
            ) sd ON true
        """
        opp_join = """
            LEFT JOIN LATERAL (
                SELECT MAX(opportunity_score) AS best_opportunity_score
                FROM opportunity_scores_v2 os
                WHERE os.market_id=mum.market_id
                  AND os.created_at >= now() - interval '7 days'
            ) os ON true
        """ if _table_exists(conn, "opportunity_scores_v2") else """
            LEFT JOIN LATERAL (SELECT NULL::numeric AS best_opportunity_score) os ON true
        """
        action_join = """
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) FILTER (WHERE evidence::text ILIKE '%%PAPER_OBSERVATION%%' OR status::text ILIKE '%%PAPER_OBSERVATION%%') AS paper_observation_interest_count,
                    COUNT(*) FILTER (WHERE status::text ILIKE '%%ACTIONABLE_SMALL_PAPER%%' OR evidence::text ILIKE '%%ACTIONABLE_SMALL_PAPER%%') AS full_paper_ready_count
                FROM paper_eligibility_candidates pec
                WHERE pec.market_id=mum.market_id
            ) pa ON true
        """ if _table_exists(conn, "paper_eligibility_candidates") else """
            LEFT JOIN LATERAL (SELECT 0::integer AS paper_observation_interest_count, 0::integer AS full_paper_ready_count) pa ON true
        """
        rows = conn.execute(
            f"""
            SELECT
                mum.*,
                ev.recent_direct_event_count,
                ev.recent_likely_event_count,
                rv.recent_revalidation_count,
                rv.latest_liquidity_state,
                rv.latest_spread_state,
                rv.latest_payout_odds_state,
                rv.latest_movement_state,
                sd.recent_candidate_seed_count,
                sd.recent_yes_seed_count,
                sd.recent_no_seed_count,
                os.best_opportunity_score,
                pa.paper_observation_interest_count,
                pa.full_paper_ready_count
            FROM market_universe_memory mum
            {event_join}
            {reval_join}
            {seed_join}
            {opp_join}
            {action_join}
            ORDER BY mum.active DESC, mum.research_priority, mum.updated_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _upsert_watchlist(self, conn: Any, record: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO research_priority_watchlist (
                research_watchlist_id, priority_run_id, market_memory_id, market_id, condition_id,
                priority_band, priority_score, refresh_cadence_seconds, next_refresh_due_at,
                last_refresh_requested_at, last_refresh_completed_at, market_status, token_verification_state,
                recent_direct_event_count, recent_likely_event_count, recent_revalidation_count,
                recent_candidate_seed_count, recent_yes_seed_count, recent_no_seed_count,
                best_opportunity_score, paper_observation_interest_count, full_paper_ready_count,
                liquidity_state, spread_state, volume_state, movement_state, payout_odds_state,
                time_to_close_seconds, closing_soon, priority_reasons_json, demotion_reasons_json,
                required_to_upgrade_json, score_components_json, evidence_inputs_json, scheduler_state
            )
            VALUES (
                %(research_watchlist_id)s, %(priority_run_id)s, %(market_memory_id)s, %(market_id)s, %(condition_id)s,
                %(priority_band)s, %(priority_score)s, %(refresh_cadence_seconds)s, %(next_refresh_due_at)s,
                %(last_refresh_requested_at)s, %(last_refresh_completed_at)s, %(market_status)s, %(token_verification_state)s,
                %(recent_direct_event_count)s, %(recent_likely_event_count)s, %(recent_revalidation_count)s,
                %(recent_candidate_seed_count)s, %(recent_yes_seed_count)s, %(recent_no_seed_count)s,
                %(best_opportunity_score)s, %(paper_observation_interest_count)s, %(full_paper_ready_count)s,
                %(liquidity_state)s, %(spread_state)s, %(volume_state)s, %(movement_state)s, %(payout_odds_state)s,
                %(time_to_close_seconds)s, %(closing_soon)s, %(priority_reasons_json)s, %(demotion_reasons_json)s,
                %(required_to_upgrade_json)s, %(score_components_json)s, %(evidence_inputs_json)s, %(scheduler_state)s
            )
            ON CONFLICT (research_watchlist_id) DO UPDATE SET
                priority_run_id=EXCLUDED.priority_run_id,
                market_id=EXCLUDED.market_id,
                condition_id=EXCLUDED.condition_id,
                priority_band=EXCLUDED.priority_band,
                priority_score=EXCLUDED.priority_score,
                refresh_cadence_seconds=EXCLUDED.refresh_cadence_seconds,
                next_refresh_due_at=EXCLUDED.next_refresh_due_at,
                last_refresh_completed_at=EXCLUDED.last_refresh_completed_at,
                market_status=EXCLUDED.market_status,
                token_verification_state=EXCLUDED.token_verification_state,
                recent_direct_event_count=EXCLUDED.recent_direct_event_count,
                recent_likely_event_count=EXCLUDED.recent_likely_event_count,
                recent_revalidation_count=EXCLUDED.recent_revalidation_count,
                recent_candidate_seed_count=EXCLUDED.recent_candidate_seed_count,
                recent_yes_seed_count=EXCLUDED.recent_yes_seed_count,
                recent_no_seed_count=EXCLUDED.recent_no_seed_count,
                best_opportunity_score=EXCLUDED.best_opportunity_score,
                paper_observation_interest_count=EXCLUDED.paper_observation_interest_count,
                full_paper_ready_count=EXCLUDED.full_paper_ready_count,
                liquidity_state=EXCLUDED.liquidity_state,
                spread_state=EXCLUDED.spread_state,
                volume_state=EXCLUDED.volume_state,
                movement_state=EXCLUDED.movement_state,
                payout_odds_state=EXCLUDED.payout_odds_state,
                time_to_close_seconds=EXCLUDED.time_to_close_seconds,
                closing_soon=EXCLUDED.closing_soon,
                priority_reasons_json=EXCLUDED.priority_reasons_json,
                demotion_reasons_json=EXCLUDED.demotion_reasons_json,
                required_to_upgrade_json=EXCLUDED.required_to_upgrade_json,
                score_components_json=EXCLUDED.score_components_json,
                evidence_inputs_json=EXCLUDED.evidence_inputs_json,
                scheduler_state=EXCLUDED.scheduler_state,
                updated_at=now()
            """,
            {
                **record,
                "priority_reasons_json": Jsonb(record.get("priority_reasons_json") or []),
                "demotion_reasons_json": Jsonb(record.get("demotion_reasons_json") or []),
                "required_to_upgrade_json": Jsonb(record.get("required_to_upgrade_json") or []),
                "score_components_json": Jsonb(record.get("score_components_json") or {}),
                "evidence_inputs_json": Jsonb(record.get("evidence_inputs_json") or {}),
            },
        )

    def _insert_run(self, conn: Any, *, priority_run_id: str, status: str, started_at: datetime, completed_at: datetime, latest_error: str | None, metadata: dict[str, Any], **stats: Any) -> None:
        conn.execute(
            """
            INSERT INTO research_priority_watchlist_runs (
                priority_run_id, status, started_at, completed_at, markets_seen, markets_updated,
                high_count, medium_count, low_count, dormant_count, archived_count, due_now_count,
                latest_error, metadata_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (priority_run_id) DO UPDATE SET
                status=EXCLUDED.status,
                completed_at=EXCLUDED.completed_at,
                markets_seen=EXCLUDED.markets_seen,
                markets_updated=EXCLUDED.markets_updated,
                high_count=EXCLUDED.high_count,
                medium_count=EXCLUDED.medium_count,
                low_count=EXCLUDED.low_count,
                dormant_count=EXCLUDED.dormant_count,
                archived_count=EXCLUDED.archived_count,
                due_now_count=EXCLUDED.due_now_count,
                latest_error=EXCLUDED.latest_error,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            (
                priority_run_id,
                status,
                started_at,
                completed_at,
                int(stats.get("markets_seen") or 0),
                int(stats.get("markets_updated") or 0),
                int(stats.get("high_count") or 0),
                int(stats.get("medium_count") or 0),
                int(stats.get("low_count") or 0),
                int(stats.get("dormant_count") or 0),
                int(stats.get("archived_count") or 0),
                int(stats.get("due_now_count") or 0),
                latest_error,
                Jsonb(_jsonable(metadata)),
            ),
        )

    def _counts(self, conn: Any) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_watchlist_rows,
                COUNT(*) FILTER (WHERE priority_band='HIGH') AS high_count,
                COUNT(*) FILTER (WHERE priority_band='MEDIUM') AS medium_count,
                COUNT(*) FILTER (WHERE priority_band='LOW') AS low_count,
                COUNT(*) FILTER (WHERE priority_band='DORMANT') AS dormant_count,
                COUNT(*) FILTER (WHERE priority_band='ARCHIVED') AS archived_count,
                COUNT(*) FILTER (WHERE scheduler_state='DUE') AS due_now_count,
                COUNT(*) FILTER (WHERE scheduler_state IN ('PAUSED','ERROR')) AS paused_error_count,
                AVG(priority_score) AS average_priority_score
            FROM research_priority_watchlist
            """
        ).fetchone()
        cadence = conn.execute(
            """
            SELECT refresh_cadence_seconds, COUNT(*) AS count
            FROM research_priority_watchlist
            GROUP BY refresh_cadence_seconds
            ORDER BY refresh_cadence_seconds
            """
        ).fetchall()
        out = {key: int(value or 0) if key.endswith("_count") or key == "total_watchlist_rows" else value for key, value in dict(row).items()}
        out["average_priority_score"] = round(float(out.get("average_priority_score") or 0.0), 2)
        out["refresh_cadence_counts"] = {str(item["refresh_cadence_seconds"]): int(item["count"] or 0) for item in cadence}
        return out

    def _sample(self, conn: Any, where: str, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"""
            SELECT *
            FROM research_priority_watchlist
            WHERE {where}
            ORDER BY priority_score DESC, updated_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _due_rows(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM research_priority_watchlist
            WHERE scheduler_state='DUE'
            ORDER BY
                CASE priority_band WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 WHEN 'LOW' THEN 2 ELSE 3 END,
                next_refresh_due_at ASC NULLS FIRST,
                priority_score DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _latest_run(self, conn: Any) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM research_priority_watchlist_runs
            ORDER BY completed_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ).fetchone()
        return _jsonable(dict(row)) if row else None

    def _ensure_tables(self, conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS research_priority_watchlist (
                id BIGSERIAL PRIMARY KEY,
                research_watchlist_id TEXT NOT NULL UNIQUE,
                priority_run_id TEXT,
                market_memory_id TEXT NOT NULL,
                market_id TEXT,
                condition_id TEXT,
                priority_band TEXT NOT NULL DEFAULT 'LOW',
                priority_score NUMERIC NOT NULL DEFAULT 0,
                refresh_cadence_seconds INTEGER NOT NULL DEFAULT 3600,
                next_refresh_due_at TIMESTAMPTZ,
                last_refresh_requested_at TIMESTAMPTZ,
                last_refresh_completed_at TIMESTAMPTZ,
                market_status TEXT NOT NULL DEFAULT 'UNRESOLVED',
                token_verification_state TEXT NOT NULL DEFAULT 'TOKENS_MISSING',
                recent_direct_event_count INTEGER NOT NULL DEFAULT 0,
                recent_likely_event_count INTEGER NOT NULL DEFAULT 0,
                recent_revalidation_count INTEGER NOT NULL DEFAULT 0,
                recent_candidate_seed_count INTEGER NOT NULL DEFAULT 0,
                recent_yes_seed_count INTEGER NOT NULL DEFAULT 0,
                recent_no_seed_count INTEGER NOT NULL DEFAULT 0,
                best_opportunity_score NUMERIC,
                paper_observation_interest_count INTEGER NOT NULL DEFAULT 0,
                full_paper_ready_count INTEGER NOT NULL DEFAULT 0,
                liquidity_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                spread_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                volume_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                movement_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                payout_odds_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                time_to_close_seconds INTEGER,
                closing_soon BOOLEAN NOT NULL DEFAULT FALSE,
                priority_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                demotion_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                required_to_upgrade_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                score_components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                evidence_inputs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                scheduler_state TEXT NOT NULL DEFAULT 'NOT_DUE',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS research_priority_watchlist_runs (
                id BIGSERIAL PRIMARY KEY,
                priority_run_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                markets_seen INTEGER NOT NULL DEFAULT 0,
                markets_updated INTEGER NOT NULL DEFAULT 0,
                high_count INTEGER NOT NULL DEFAULT 0,
                medium_count INTEGER NOT NULL DEFAULT 0,
                low_count INTEGER NOT NULL DEFAULT 0,
                dormant_count INTEGER NOT NULL DEFAULT 0,
                archived_count INTEGER NOT NULL DEFAULT 0,
                due_now_count INTEGER NOT NULL DEFAULT 0,
                latest_error TEXT,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def build_priority_profile(row: dict[str, Any], *, run_id: str = "test", now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    status = str(row.get("status") or "UNRESOLVED").upper()
    token_state = str(row.get("token_verification_state") or "TOKENS_MISSING").upper()
    liquidity_state = _liquidity_state(row)
    spread_state = _spread_state(row)
    volume_state = _volume_state(row)
    movement_state = str(row.get("latest_movement_state") or "UNKNOWN").upper()
    payout_state = str(row.get("latest_payout_odds_state") or "UNKNOWN").upper()
    direct = _int(row.get("recent_direct_event_count"))
    likely = _int(row.get("recent_likely_event_count"))
    reval = _int(row.get("recent_revalidation_count"))
    seeds = _int(row.get("recent_candidate_seed_count"))
    yes_seeds = _int(row.get("recent_yes_seed_count"))
    no_seeds = _int(row.get("recent_no_seed_count"))
    opportunity = _float(row.get("best_opportunity_score"))
    paper_obs = _int(row.get("paper_observation_interest_count"))
    full_paper = _int(row.get("full_paper_ready_count"))
    time_to_close = _time_to_close_seconds(row.get("close_time"), now)
    closing_soon = time_to_close is not None and 0 <= time_to_close <= 7 * 24 * 3600

    components = {
        "event_heat_score": min(30, direct * 20 + likely * 12),
        "revalidation_score": min(15, reval * 6),
        "candidate_seed_score": min(20, seeds * 10),
        "opportunity_score_component": min(15, max(0.0, opportunity or 0.0) * 0.15),
        "liquidity_component": {"GOOD": 10, "MEDIUM": 7, "POOR": 1, "UNKNOWN": 0}.get(liquidity_state, 0),
        "spread_component": {"TIGHT": 8, "MEDIUM": 5, "WIDE": 1, "UNKNOWN": 0}.get(spread_state, 0),
        "volume_component": {"HIGH": 8, "MEDIUM": 5, "LOW": 1, "UNKNOWN": 0}.get(volume_state, 0),
        "movement_component": {"ACTIVE": 7, "QUIET": 1, "UNKNOWN": 0}.get(_movement_priority_state(movement_state), 0),
        "closing_soon_component": 10 if closing_soon else 0,
        "paper_observation_interest_component": min(15, paper_obs * 10 + full_paper * 15),
        "thesis_edge_component": 0,
        "stale_penalty": 8 if str(row.get("freshness_state") or "").upper() in {"STALE", "NEEDS_REFRESH"} else 0,
        "identity_problem_penalty": 15 if str(row.get("identity_verification_state") or "").upper() != "VERIFIED" else 0,
        "token_problem_penalty": 25 if token_state in {"TOKENS_MISMATCH", "TOKENS_MISSING"} else 10 if token_state == "TOKENS_PARTIAL" else 0,
        "low_liquidity_penalty": 8 if liquidity_state == "POOR" else 0,
        "repeated_no_signal_penalty": 8 if direct == likely == seeds == reval == 0 and liquidity_state in {"POOR", "UNKNOWN"} else 0,
    }
    positive = sum(float(components[key]) for key in (
        "event_heat_score",
        "revalidation_score",
        "candidate_seed_score",
        "opportunity_score_component",
        "liquidity_component",
        "spread_component",
        "volume_component",
        "movement_component",
        "closing_soon_component",
        "paper_observation_interest_component",
        "thesis_edge_component",
    ))
    penalty = sum(float(components[key]) for key in (
        "stale_penalty",
        "identity_problem_penalty",
        "token_problem_penalty",
        "low_liquidity_penalty",
        "repeated_no_signal_penalty",
    ))
    score = round(max(0.0, min(100.0, positive - penalty)), 2)
    reasons, demotions, required = _reasons(row, components, status=status, token_state=token_state, closing_soon=closing_soon)
    band = _band(status=status, score=score, direct=direct, likely=likely, seeds=seeds, liquidity_state=liquidity_state, token_state=token_state)
    cadence = CADENCE_BY_BAND.get(band, 3600)
    next_due = None if cadence <= 0 else now + timedelta(seconds=cadence)
    scheduler_state = "ARCHIVED" if band == "ARCHIVED" else "NOT_DUE"
    return {
        "research_watchlist_id": _watchlist_id(row.get("market_memory_id"), row.get("market_id")),
        "priority_run_id": run_id,
        "market_memory_id": row.get("market_memory_id"),
        "market_id": row.get("market_id"),
        "condition_id": row.get("condition_id"),
        "priority_band": band,
        "priority_score": score,
        "refresh_cadence_seconds": cadence,
        "next_refresh_due_at": next_due,
        "last_refresh_requested_at": None,
        "last_refresh_completed_at": None,
        "market_status": status,
        "token_verification_state": token_state,
        "recent_direct_event_count": direct,
        "recent_likely_event_count": likely,
        "recent_revalidation_count": reval,
        "recent_candidate_seed_count": seeds,
        "recent_yes_seed_count": yes_seeds,
        "recent_no_seed_count": no_seeds,
        "best_opportunity_score": opportunity,
        "paper_observation_interest_count": paper_obs,
        "full_paper_ready_count": full_paper,
        "liquidity_state": liquidity_state,
        "spread_state": spread_state,
        "volume_state": volume_state,
        "movement_state": _movement_priority_state(movement_state),
        "payout_odds_state": payout_state,
        "time_to_close_seconds": time_to_close,
        "closing_soon": closing_soon,
        "priority_reasons_json": reasons,
        "demotion_reasons_json": demotions,
        "required_to_upgrade_json": required,
        "score_components_json": components,
        "evidence_inputs_json": _jsonable({
            "market_memory_id": row.get("market_memory_id"),
            "market_id": row.get("market_id"),
            "direct_events": direct,
            "likely_events": likely,
            "revalidations": reval,
            "candidate_seeds": seeds,
            "opportunity_score": opportunity,
        }),
        "scheduler_state": scheduler_state,
    }


def priority_formula() -> str:
    return (
        "priority_score = event_heat + revalidation + candidate_seed + opportunity + liquidity + spread + "
        "volume + movement + closing_soon + paper_observation + thesis_edge - stale - identity_problem - "
        "token_problem - low_liquidity - repeated_no_signal"
    )


def _band(*, status: str, score: float, direct: int, likely: int, seeds: int, liquidity_state: str, token_state: str) -> str:
    if status in {"CLOSED", "RESOLVED", "ARCHIVED"}:
        return "ARCHIVED"
    if token_state == "TOKENS_MISMATCH":
        return "LOW"
    if score >= 60 and (direct > 0 or likely > 0 or seeds > 0) and liquidity_state in {"GOOD", "MEDIUM"}:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    if score >= 12:
        return "LOW"
    if status == "ACTIVE":
        return "DORMANT"
    return "LOW"


def _reasons(row: dict[str, Any], components: dict[str, Any], *, status: str, token_state: str, closing_soon: bool) -> tuple[list[str], list[str], list[str]]:
    reasons: list[str] = []
    demotions: list[str] = []
    required: list[str] = []
    if components["event_heat_score"]:
        reasons.append("RECENT_STRONG_EVENT_LINKS")
    if components["candidate_seed_score"]:
        reasons.append("RECENT_PROACTIVE_CANDIDATE_SEEDS")
    if components["revalidation_score"]:
        reasons.append("RECENT_TARGETED_REVALIDATION")
    if components["liquidity_component"]:
        reasons.append("USABLE_LIQUIDITY")
    if components["spread_component"]:
        reasons.append("USABLE_SPREAD")
    if closing_soon:
        reasons.append("CLOSING_SOON")
    if components["paper_observation_interest_component"]:
        reasons.append("PAPER_OBSERVATION_OR_FULL_PAPER_INTEREST")
    if status in {"CLOSED", "RESOLVED", "ARCHIVED"}:
        demotions.append("MARKET_TERMINAL_ARCHIVED")
    if token_state != "TOKENS_VERIFIED":
        demotions.append(token_state)
        required.append("Verify YES/NO tokens before increasing research priority.")
    if components["stale_penalty"]:
        demotions.append("MARKET_MEMORY_STALE")
        required.append("Refresh Market Universe Memory.")
    if components["low_liquidity_penalty"]:
        demotions.append("LOW_LIQUIDITY")
        required.append("Collect improved liquidity/depth evidence.")
    if components["repeated_no_signal_penalty"]:
        demotions.append("NO_RECENT_SIGNAL_HEAT")
        required.append("Wait for stronger source events, movement, or candidate seeds.")
    return _dedupe(reasons), _dedupe(demotions), _dedupe(required)


def _liquidity_state(row: dict[str, Any]) -> str:
    explicit = str(row.get("latest_liquidity_state") or "").upper()
    if explicit in {"GOOD", "MEDIUM", "POOR", "UNKNOWN"}:
        return explicit
    value = _float(row.get("liquidity"))
    if value is None:
        return "UNKNOWN"
    if value >= 500 or value >= 0.6:
        return "GOOD"
    if value >= 100 or value >= 0.25:
        return "MEDIUM"
    if value > 0:
        return "POOR"
    return "UNKNOWN"


def _spread_state(row: dict[str, Any]) -> str:
    explicit = str(row.get("latest_spread_state") or "").upper()
    if explicit in {"TIGHT", "MEDIUM", "WIDE", "UNKNOWN"}:
        return explicit
    value = _float(row.get("spread"))
    if value is None:
        return "UNKNOWN"
    if value <= 0.02:
        return "TIGHT"
    if value <= 0.05:
        return "MEDIUM"
    return "WIDE"


def _volume_state(row: dict[str, Any]) -> str:
    value = _float(row.get("volume"))
    if value is None:
        return "UNKNOWN"
    if value >= 1000:
        return "HIGH"
    if value >= 100:
        return "MEDIUM"
    if value > 0:
        return "LOW"
    return "UNKNOWN"


def _movement_priority_state(value: str) -> str:
    if value in {"MOVED_AFTER_EVENT", "ALREADY_MOVED_BEFORE_EVENT", "ACTIVE"}:
        return "ACTIVE"
    if value in {"NO_CLEAR_MOVE", "QUIET"}:
        return "QUIET"
    return "UNKNOWN"


def _time_to_close_seconds(value: Any, now: datetime) -> int | None:
    if not value:
        return None
    dt = value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int((dt.astimezone(UTC) - now).total_seconds())


def _watchlist_id(market_memory_id: Any, market_id: Any) -> str:
    key = str(market_memory_id or market_id or uuid4().hex)
    return f"research_watchlist_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:28]}"


def _empty_summary(status: str, now: datetime) -> dict[str, Any]:
    return {
        "status": status,
        "source": "research_priority_watchlist",
        "last_updated": now.isoformat(),
        "freshness_state": "MISSING",
        "readiness_state": "UNKNOWN",
        "truth_state": "UNKNOWN",
        "counts": {},
        "warnings": ["Research priority watchlist is unavailable."],
        "errors": [],
    }


def _empty_market_fields() -> dict[str, Any]:
    return {
        "research_watchlist_id": None,
        "research_priority_band": None,
        "research_priority_score": None,
        "next_refresh_due_at": None,
        "refresh_cadence_seconds": None,
        "watchlist_scheduler_state": None,
        "watchlist_reason": None,
        "priority_reasons": [],
        "demotion_reasons": [],
        "mesh_inquiry_count": 0,
        "mesh_completed_count": 0,
        "best_seed_opportunity_score": None,
        "paper_observation_interest_from_seed_mesh": 0,
    }


def _safety_counts(conn: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "positions", "shadow_orders", "fresh_candidate_seeds", "market_link_candidates", "paper_eligibility_candidates"):
        if _table_exists(conn, table):
            out[table] = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
        else:
            out[table] = 0
    return out


def _trading_mutation(before: dict[str, int], after: dict[str, int]) -> bool:
    watched = {"paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "positions", "shadow_orders", "fresh_candidate_seeds", "market_link_candidates"}
    return any(after.get(table, 0) != before.get(table, 0) for table in watched)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row.get("reg"))


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else str(value) if value is not None else None


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out
