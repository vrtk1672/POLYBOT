from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory


DIRECT_CONFIDENCE_THRESHOLD = 0.75
LIKELY_CONFIDENCE_THRESHOLD = 0.70
DEFAULT_REFRESH_LIMIT = 50
DEFAULT_SKIPPED_SAMPLE_LIMIT = 20
REVALIDATION_TTL_SECONDS = 900
ORDERBOOK_TTL_SECONDS = 180
RECENT_EVENT_WINDOW_HOURS = 72

ELIGIBLE_LINK_TYPES = {"DIRECT_LINK", "LIKELY_LINK"}
SKIPPED_LINK_TYPES = {"WEAK_LINK", "CONTEXT_ONLY", "NO_LINK"}
SKIPPED_HINTS = {
    "WATCH_ONLY",
    "CONTEXT_ONLY",
    "NOT_RELEVANT",
    "BLOCKED_BY_LOW_CONFIDENCE",
    "BLOCKED_BY_TOKEN_SIDE_UNKNOWN",
    "BLOCKED_BY_CONFLICT",
}

TOKEN_SIDE_CANDIDATE_SCOPED = {"TOKEN_SIDE_DIRECT", "SIDE_DIRECTIONAL_YES", "SIDE_DIRECTIONAL_NO"}
TOKEN_SIDE_MARKET_LEVEL = {"MARKET_LEVEL_ONLY", "TOKEN_SIDE_UNKNOWN", "SIDE_DIRECTIONAL_NEUTRAL", "SIDE_DIRECTIONAL_MIXED"}


class TargetedMarketRevalidationService:
    """DATA_ONLY targeted market revalidation from source-event recall.

    Stage 3 consumes Stage 2.5 event-to-market recall rows, refreshes current
    market truth from existing local evidence, and writes revalidation truth.
    It never creates execution candidates, paper artifacts, live artifacts, or
    trade approvals.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def refresh(
        self,
        *,
        limit: int = DEFAULT_REFRESH_LIMIT,
        force: bool = False,
        skipped_sample_limit: int = DEFAULT_SKIPPED_SAMPLE_LIMIT,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"targeted_market_revalidation_{uuid4().hex}"
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "refresh_run_id": run_id, "eligible_links_seen": 0}
        limit = max(1, min(int(limit or DEFAULT_REFRESH_LIMIT), 500))
        skipped_sample_limit = max(0, min(int(skipped_sample_limit or 0), 100))
        with self._factory.connect() as conn, conn.transaction():
            self._ensure_tables(conn)
            safety_before = _safety_counts(conn)
            eligible_live_count = self._eligible_links_count(conn)
            links = self._eligible_links(conn, limit=limit, force=force)
            skipped = self._skipped_links(conn, limit=skipped_sample_limit)
            stats = {
                "eligible_links_seen": int(eligible_live_count),
                "links_revalidated": 0,
                "links_skipped": 0,
                "links_failed": 0,
                "links_partial": 0,
                "markets_refreshed": 0,
            }
            errors: list[str] = []
            refreshed_markets: set[str] = set()
            for link in skipped:
                try:
                    self._write_skipped(conn, link, run_id=run_id, started_at=started_at, reason=_skip_reason(link))
                    stats["links_skipped"] += 1
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    stats["links_failed"] += 1
            for link in links:
                try:
                    result = self._revalidate_link(conn, link, run_id=run_id, started_at=started_at)
                    state = str(result.get("revalidation_state") or "FAILED")
                    stats["links_revalidated"] += int(state == "REVALIDATED")
                    stats["links_partial"] += int(state == "PARTIAL")
                    stats["links_failed"] += int(state == "FAILED")
                    if result.get("market_id"):
                        refreshed_markets.add(str(result["market_id"]))
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    stats["links_failed"] += 1
            stats["markets_refreshed"] = len(refreshed_markets)
            safety_after = _safety_counts(conn)
            completed_at = datetime.now(UTC)
            status = "OK" if not errors else "PARTIAL" if (stats["links_revalidated"] or stats["links_partial"] or stats["links_skipped"]) else "ERROR"
            self._insert_refresh_run(
                conn,
                refresh_run_id=run_id,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                latest_error=errors[0] if errors else None,
                metadata={
                    "limit": limit,
                    "force": force,
                    "skipped_sample_limit": skipped_sample_limit,
                    "safety_before": safety_before,
                    "safety_after": safety_after,
                    "trading_mutation": _trading_mutation(safety_before, safety_after),
                    "execution_candidates_created": False,
                    "paper_artifacts_created": False,
                    "errors": errors[:5],
                },
                **stats,
            )
        return {
            "status": status,
            "refresh_run_id": run_id,
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
            latest = self._latest_refresh_run(conn)
            top_revalidated = self._sample(conn, "revalidation_state IN ('REVALIDATED','PARTIAL')", limit=limit)
            top_skipped = self._sample(conn, "revalidation_state='SKIPPED'", limit=limit)
            top_failures = self._sample(conn, "revalidation_state='FAILED'", limit=limit)
        return {
            "status": "REAL" if counts["total_revalidation_rows"] else "MISSING",
            "source": "targeted_market_revalidation + source_event_memory + market_universe_memory + orderbook truth",
            "last_updated": (latest or {}).get("completed_at") or now.isoformat(),
            "freshness_state": "FRESH" if latest and counts["total_revalidation_rows"] else "MISSING",
            "readiness_state": "READY" if counts["total_revalidation_rows"] else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if counts["total_revalidation_rows"] else "UNKNOWN",
            "counts": counts,
            "latest_refresh": _jsonable(latest),
            "top_revalidated_markets": top_revalidated,
            "top_skipped_links": top_skipped,
            "top_failures": top_failures,
            "warnings": [] if counts["total_revalidation_rows"] else ["No targeted market revalidation rows have been created yet."],
            "errors": [],
            "generated_at": now.isoformat(),
        }

    def by_market(self, *, market_id: str, limit: int = 20) -> dict[str, Any]:
        if not market_id:
            return {"status": "BLOCKED", "blocker": "MARKET_ID_REQUIRED", "results": []}
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "results": []}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM targeted_market_revalidations
                WHERE market_id=%s
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (market_id, limit),
            ).fetchall()
        return {"status": "REAL", "market_id": market_id, "results": [_jsonable(dict(row)) for row in rows]}

    def by_event(self, *, source_event_id: str, limit: int = 50) -> dict[str, Any]:
        if not source_event_id:
            return {"status": "BLOCKED", "blocker": "SOURCE_EVENT_ID_REQUIRED", "results": []}
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "source_event": None, "results": []}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            event = conn.execute("SELECT * FROM source_event_memory WHERE source_event_id=%s LIMIT 1", (source_event_id,)).fetchone() if _table_exists(conn, "source_event_memory") else None
            rows = conn.execute(
                """
                SELECT *
                FROM targeted_market_revalidations
                WHERE source_event_id=%s
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (source_event_id, limit),
            ).fetchall()
        return {
            "status": "REAL" if event or rows else "MISSING",
            "source_event": _jsonable(dict(event)) if event else None,
            "results": [_jsonable(dict(row)) for row in rows],
        }

    def fields_for_market(self, *, market_id: str | None) -> dict[str, Any]:
        if not market_id or not self._factory.enabled:
            return _empty_market_fields()
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                """
                SELECT *
                FROM targeted_market_revalidations
                WHERE market_id=%s
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
            counts = conn.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE updated_at >= now() - interval '72 hours') AS recent_revalidated_event_count,
                    COUNT(*) FILTER (WHERE eligible_for_candidate_generation_later IS TRUE AND updated_at >= now() - interval '72 hours') AS candidate_generation_later_eligible_count
                FROM targeted_market_revalidations
                WHERE market_id=%s
                """,
                (market_id,),
            ).fetchone()
        if not row:
            return _empty_market_fields()
        item = dict(row)
        try:
            from app.services.proactive_seed_mesh_inquiry import ProactiveSeedMeshInquiryService

            mesh_fields = ProactiveSeedMeshInquiryService(connection_factory=self._factory).fields_for_market(market_id=market_id)
        except Exception:
            mesh_fields = {"seed_mesh_inquiry_count": 0, "seed_mesh_best_score": None}
        return {
            "targeted_revalidation_id": item.get("targeted_revalidation_id"),
            "latest_targeted_revalidation_state": item.get("revalidation_state"),
            "latest_targeted_revalidation_at": _iso(item.get("updated_at") or item.get("completed_at")),
            "orderbook_refresh_state_from_revalidation": item.get("orderbook_refresh_state"),
            "refreshed_orderbook_snapshot_id": item.get("selected_orderbook_snapshot_id"),
            "movement_state_from_revalidation": item.get("movement_state"),
            "already_priced_in_state_from_revalidation": item.get("already_priced_in_state"),
            "revalidation_candidate_generation_later_state": "ELIGIBLE" if item.get("eligible_for_candidate_generation_later") else "NOT_ELIGIBLE",
            "candidate_generation_later_eligible": bool(item.get("eligible_for_candidate_generation_later")),
            "recent_revalidated_event_count": int((counts or {}).get("recent_revalidated_event_count") or 0),
            "candidate_generation_later_eligible_count": int((counts or {}).get("candidate_generation_later_eligible_count") or 0),
            "downstream_seed_mesh_count": mesh_fields.get("seed_mesh_inquiry_count", 0),
            "best_downstream_seed_score": mesh_fields.get("seed_mesh_best_score"),
        }

    def _eligible_links_count(self, conn: Any) -> int:
        if not _table_exists(conn, "event_to_market_recall"):
            return 0
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM event_to_market_recall
            WHERE market_id IS NOT NULL
              AND candidate_actionability_hint='REVALIDATION_ELIGIBLE'
              AND (
                    (link_type='DIRECT_LINK' AND link_confidence >= %s)
                 OR (link_type='LIKELY_LINK' AND link_confidence >= %s)
              )
            """,
            (DIRECT_CONFIDENCE_THRESHOLD, LIKELY_CONFIDENCE_THRESHOLD),
        ).fetchone()
        return int((row or {}).get("count") or 0)

    def _eligible_links(self, conn: Any, *, limit: int, force: bool) -> list[dict[str, Any]]:
        if not _table_exists(conn, "event_to_market_recall"):
            return []
        skip_recent_clause = "" if force else """
          AND NOT EXISTS (
              SELECT 1
              FROM targeted_market_revalidations tmr
              WHERE tmr.event_to_market_link_id=emr.recall_id
                AND tmr.updated_at >= now() - (%s || ' seconds')::interval
          )
        """
        params: list[Any] = [DIRECT_CONFIDENCE_THRESHOLD, LIKELY_CONFIDENCE_THRESHOLD]
        if not force:
            params.append(REVALIDATION_TTL_SECONDS)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT emr.*, sem.event_timestamp, sem.direction AS event_direction,
                   sem.already_priced_in_state AS event_already_priced_in_state,
                   sem.headline AS source_event_headline
            FROM event_to_market_recall emr
            LEFT JOIN source_event_memory sem ON sem.source_event_id=emr.source_event_id
            WHERE emr.market_id IS NOT NULL
              AND emr.candidate_actionability_hint='REVALIDATION_ELIGIBLE'
              AND (
                    (emr.link_type='DIRECT_LINK' AND emr.link_confidence >= %s)
                 OR (emr.link_type='LIKELY_LINK' AND emr.link_confidence >= %s)
              )
              {skip_recent_clause}
            ORDER BY emr.link_confidence DESC, emr.updated_at DESC, emr.id DESC
            LIMIT %s
            """,
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]

    def _skipped_links(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        if limit <= 0 or not _table_exists(conn, "event_to_market_recall"):
            return []
        rows = conn.execute(
            """
            SELECT emr.*, sem.event_timestamp, sem.direction AS event_direction,
                   sem.already_priced_in_state AS event_already_priced_in_state,
                   sem.headline AS source_event_headline
            FROM event_to_market_recall emr
            LEFT JOIN source_event_memory sem ON sem.source_event_id=emr.source_event_id
            WHERE emr.market_id IS NOT NULL
              AND (
                    emr.link_type IN ('WEAK_LINK','CONTEXT_ONLY','NO_LINK')
                 OR emr.candidate_actionability_hint IN ('WATCH_ONLY','CONTEXT_ONLY','NOT_RELEVANT','BLOCKED_BY_LOW_CONFIDENCE','BLOCKED_BY_TOKEN_SIDE_UNKNOWN','BLOCKED_BY_CONFLICT')
                 OR (emr.link_type='LIKELY_LINK' AND emr.link_confidence < %s)
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM targeted_market_revalidations tmr
                  WHERE tmr.event_to_market_link_id=emr.recall_id
                    AND tmr.updated_at >= now() - (%s || ' seconds')::interval
              )
            ORDER BY emr.updated_at DESC, emr.link_confidence DESC, emr.id DESC
            LIMIT %s
            """,
            (LIKELY_CONFIDENCE_THRESHOLD, REVALIDATION_TTL_SECONDS, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _revalidate_link(self, conn: Any, link: dict[str, Any], *, run_id: str, started_at: datetime) -> dict[str, Any]:
        market = _market_memory_row(conn, link)
        if not market:
            result = self._base_record(link, run_id=run_id, started_at=started_at)
            result.update(
                {
                    "revalidation_state": "FAILED",
                    "failure_reason": "MARKET_MEMORY_ROW_MISSING",
                    "required_to_pass_json": ["Refresh Market Universe Memory for this recalled market."],
                }
            )
            self._upsert_revalidation(conn, result)
            return result
        orderbook = _latest_orderbook(conn, market, token_side_state=str(link.get("token_side_resolution_state") or "TOKEN_SIDE_UNKNOWN"), direction=str(link.get("direction_for_market") or "UNKNOWN"))
        payout = _latest_payout(conn, market.get("market_id"))
        movement = _movement_state(conn, market.get("market_id"), link.get("event_timestamp"))
        signal_state = _signal_state(conn, market.get("market_id"))
        identity_state = _identity_state(market)
        token_state = str(market.get("token_verification_state") or "TOKENS_MISSING")
        token_side_state = str(link.get("token_side_resolution_state") or "TOKEN_SIDE_UNKNOWN")
        candidate_scope = _candidate_event_scope_state(token_side_state, token_state)
        metadata_state = _metadata_state(market)
        orderbook_state = orderbook["orderbook_refresh_state"]
        already_priced_in, priced_reason = _already_priced_in_state(link, movement)
        blockers = _candidate_generation_blockers(
            market=market,
            identity_state=identity_state,
            token_state=token_state,
            token_side_state=token_side_state,
            orderbook_state=orderbook_state,
            liquidity_state=orderbook["liquidity_state"],
            link=link,
            candidate_scope=candidate_scope,
            already_priced_in=already_priced_in,
        )
        state = "REVALIDATED" if identity_state == "VERIFIED" and token_state == "TOKENS_VERIFIED" and orderbook_state == "FRESH" else "PARTIAL"
        result = self._base_record(link, run_id=run_id, started_at=started_at)
        result.update(
            {
                "market_memory_id": market.get("market_memory_id"),
                "market_id": market.get("market_id"),
                "condition_id": market.get("condition_id"),
                "revalidation_state": state,
                "market_identity_state": identity_state,
                "token_verification_state": token_state,
                "token_side_resolution_state": token_side_state,
                "metadata_refresh_state": metadata_state,
                "orderbook_refresh_state": orderbook_state,
                "selected_orderbook_snapshot_id": orderbook.get("selected_orderbook_snapshot_id"),
                "liquidity_state": orderbook["liquidity_state"],
                "spread_state": orderbook["spread_state"],
                "payout_odds_state": payout["payout_odds_state"],
                "movement_state": movement["movement_state"],
                "signal_state": signal_state,
                "candidate_event_scope_state": candidate_scope,
                "already_priced_in_state": already_priced_in,
                "already_priced_in_reason": priced_reason,
                "eligible_for_candidate_generation_later": len(blockers) == 0,
                "candidate_generation_blockers_json": blockers,
                "required_to_pass_json": _required_to_pass(blockers),
                "metadata_json": {
                    "source_event_headline": link.get("source_event_headline"),
                    "event_timestamp": _iso(link.get("event_timestamp")),
                    "link_reason": link.get("reason"),
                    "movement": movement,
                    "orderbook": orderbook,
                    "payout": payout,
                    "stage3_execution_triggered": False,
                    "candidate_created": False,
                },
            }
        )
        self._upsert_revalidation(conn, result)
        return result

    def _write_skipped(self, conn: Any, link: dict[str, Any], *, run_id: str, started_at: datetime, reason: str) -> None:
        result = self._base_record(link, run_id=run_id, started_at=started_at)
        result.update(
            {
                "revalidation_state": "SKIPPED",
                "skip_reason": reason,
                "token_side_resolution_state": str(link.get("token_side_resolution_state") or "TOKEN_SIDE_UNKNOWN"),
                "metadata_json": {
                    "link_type": link.get("link_type"),
                    "candidate_actionability_hint": link.get("candidate_actionability_hint"),
                    "guardrail_reason": link.get("guardrail_reason"),
                    "stage3_execution_triggered": False,
                    "candidate_created": False,
                },
                "candidate_generation_blockers_json": [reason],
                "required_to_pass_json": _required_to_pass([reason]),
            }
        )
        self._upsert_revalidation(conn, result)

    def _base_record(self, link: dict[str, Any], *, run_id: str, started_at: datetime) -> dict[str, Any]:
        completed_at = datetime.now(UTC)
        recall_id = str(link.get("recall_id") or link.get("event_to_market_link_id") or "")
        return {
            "targeted_revalidation_id": _revalidation_id(recall_id, started_at),
            "refresh_run_id": run_id,
            "source_event_id": str(link.get("source_event_id") or ""),
            "event_to_market_link_id": recall_id,
            "market_memory_id": link.get("market_memory_id"),
            "market_id": link.get("market_id"),
            "condition_id": link.get("condition_id"),
            "link_type": str(link.get("link_type") or "UNKNOWN"),
            "link_confidence": float(link.get("link_confidence") or 0.0),
            "revalidation_state": "SKIPPED",
            "skip_reason": None,
            "failure_reason": None,
            "market_identity_state": "UNRESOLVED",
            "token_verification_state": "TOKENS_MISSING",
            "token_side_resolution_state": "TOKEN_SIDE_UNKNOWN",
            "metadata_refresh_state": "NOT_AVAILABLE",
            "orderbook_refresh_state": "NOT_AVAILABLE",
            "selected_orderbook_snapshot_id": None,
            "liquidity_state": "UNKNOWN",
            "spread_state": "UNKNOWN",
            "payout_odds_state": "MISSING",
            "movement_state": "UNKNOWN",
            "signal_state": "MISSING",
            "candidate_event_scope_state": "UNKNOWN",
            "already_priced_in_state": "UNKNOWN",
            "already_priced_in_reason": None,
            "eligible_for_candidate_generation_later": False,
            "candidate_generation_blockers_json": [],
            "required_to_pass_json": [],
            "metadata_json": {},
            "started_at": started_at,
            "completed_at": completed_at,
        }

    def _upsert_revalidation(self, conn: Any, record: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO targeted_market_revalidations (
                targeted_revalidation_id, refresh_run_id, source_event_id, event_to_market_link_id,
                market_memory_id, market_id, condition_id, link_type, link_confidence,
                revalidation_state, skip_reason, failure_reason, market_identity_state,
                token_verification_state, token_side_resolution_state, metadata_refresh_state,
                orderbook_refresh_state, selected_orderbook_snapshot_id, liquidity_state,
                spread_state, payout_odds_state, movement_state, signal_state,
                candidate_event_scope_state, already_priced_in_state, already_priced_in_reason,
                eligible_for_candidate_generation_later, candidate_generation_blockers_json,
                required_to_pass_json, metadata_json, started_at, completed_at
            )
            VALUES (
                %(targeted_revalidation_id)s, %(refresh_run_id)s, %(source_event_id)s, %(event_to_market_link_id)s,
                %(market_memory_id)s, %(market_id)s, %(condition_id)s, %(link_type)s, %(link_confidence)s,
                %(revalidation_state)s, %(skip_reason)s, %(failure_reason)s, %(market_identity_state)s,
                %(token_verification_state)s, %(token_side_resolution_state)s, %(metadata_refresh_state)s,
                %(orderbook_refresh_state)s, %(selected_orderbook_snapshot_id)s, %(liquidity_state)s,
                %(spread_state)s, %(payout_odds_state)s, %(movement_state)s, %(signal_state)s,
                %(candidate_event_scope_state)s, %(already_priced_in_state)s, %(already_priced_in_reason)s,
                %(eligible_for_candidate_generation_later)s, %(candidate_generation_blockers_json)s,
                %(required_to_pass_json)s, %(metadata_json)s, %(started_at)s, %(completed_at)s
            )
            ON CONFLICT (targeted_revalidation_id) DO UPDATE SET
                refresh_run_id=EXCLUDED.refresh_run_id,
                revalidation_state=EXCLUDED.revalidation_state,
                skip_reason=EXCLUDED.skip_reason,
                failure_reason=EXCLUDED.failure_reason,
                market_identity_state=EXCLUDED.market_identity_state,
                token_verification_state=EXCLUDED.token_verification_state,
                token_side_resolution_state=EXCLUDED.token_side_resolution_state,
                metadata_refresh_state=EXCLUDED.metadata_refresh_state,
                orderbook_refresh_state=EXCLUDED.orderbook_refresh_state,
                selected_orderbook_snapshot_id=EXCLUDED.selected_orderbook_snapshot_id,
                liquidity_state=EXCLUDED.liquidity_state,
                spread_state=EXCLUDED.spread_state,
                payout_odds_state=EXCLUDED.payout_odds_state,
                movement_state=EXCLUDED.movement_state,
                signal_state=EXCLUDED.signal_state,
                candidate_event_scope_state=EXCLUDED.candidate_event_scope_state,
                already_priced_in_state=EXCLUDED.already_priced_in_state,
                already_priced_in_reason=EXCLUDED.already_priced_in_reason,
                eligible_for_candidate_generation_later=EXCLUDED.eligible_for_candidate_generation_later,
                candidate_generation_blockers_json=EXCLUDED.candidate_generation_blockers_json,
                required_to_pass_json=EXCLUDED.required_to_pass_json,
                metadata_json=EXCLUDED.metadata_json,
                completed_at=EXCLUDED.completed_at,
                updated_at=now()
            """,
            {
                **record,
                "candidate_generation_blockers_json": Jsonb(record.get("candidate_generation_blockers_json") or []),
                "required_to_pass_json": Jsonb(record.get("required_to_pass_json") or []),
                "metadata_json": Jsonb(_jsonable(record.get("metadata_json") or {})),
            },
        )

    def _insert_refresh_run(self, conn: Any, *, refresh_run_id: str, status: str, started_at: datetime, completed_at: datetime, latest_error: str | None, metadata: dict[str, Any], **stats: Any) -> None:
        conn.execute(
            """
            INSERT INTO targeted_market_revalidation_refresh_runs (
                refresh_run_id, status, started_at, completed_at, eligible_links_seen,
                links_revalidated, links_skipped, links_failed, links_partial,
                markets_refreshed, latest_error, metadata_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (refresh_run_id) DO UPDATE SET
                status=EXCLUDED.status,
                completed_at=EXCLUDED.completed_at,
                eligible_links_seen=EXCLUDED.eligible_links_seen,
                links_revalidated=EXCLUDED.links_revalidated,
                links_skipped=EXCLUDED.links_skipped,
                links_failed=EXCLUDED.links_failed,
                links_partial=EXCLUDED.links_partial,
                markets_refreshed=EXCLUDED.markets_refreshed,
                latest_error=EXCLUDED.latest_error,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            (
                refresh_run_id,
                status,
                started_at,
                completed_at,
                int(stats.get("eligible_links_seen") or 0),
                int(stats.get("links_revalidated") or 0),
                int(stats.get("links_skipped") or 0),
                int(stats.get("links_failed") or 0),
                int(stats.get("links_partial") or 0),
                int(stats.get("markets_refreshed") or 0),
                latest_error,
                Jsonb(_jsonable(metadata)),
            ),
        )

    def _counts(self, conn: Any) -> dict[str, Any]:
        eligible = self._eligible_links_count(conn)
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_revalidation_rows,
                COUNT(*) FILTER (WHERE revalidation_state='REVALIDATED') AS revalidated_count,
                COUNT(*) FILTER (WHERE revalidation_state='PARTIAL') AS partial_count,
                COUNT(*) FILTER (WHERE revalidation_state='FAILED') AS failed_count,
                COUNT(*) FILTER (WHERE revalidation_state='SKIPPED') AS skipped_count,
                COUNT(DISTINCT market_id) FILTER (WHERE revalidation_state IN ('REVALIDATED','PARTIAL')) AS markets_refreshed_count,
                COUNT(*) FILTER (WHERE orderbook_refresh_state='FRESH') AS orderbook_fresh_count,
                COUNT(*) FILTER (WHERE orderbook_refresh_state='STALE') AS orderbook_stale_count,
                COUNT(*) FILTER (WHERE orderbook_refresh_state='FAILED') AS orderbook_failed_count,
                COUNT(*) FILTER (WHERE token_verification_state='TOKENS_VERIFIED') AS token_verified_count,
                COUNT(*) FILTER (WHERE token_verification_state='TOKENS_MISMATCH') AS token_mismatch_count,
                COUNT(*) FILTER (WHERE liquidity_state='GOOD') AS liquidity_good_count,
                COUNT(*) FILTER (WHERE liquidity_state='MEDIUM') AS liquidity_medium_count,
                COUNT(*) FILTER (WHERE liquidity_state='POOR') AS liquidity_poor_count,
                COUNT(*) FILTER (WHERE spread_state='TIGHT') AS spread_tight_count,
                COUNT(*) FILTER (WHERE spread_state='MEDIUM') AS spread_medium_count,
                COUNT(*) FILTER (WHERE spread_state='WIDE') AS spread_wide_count,
                COUNT(*) FILTER (WHERE payout_odds_state='AVAILABLE') AS payout_odds_available_count,
                COUNT(*) FILTER (WHERE payout_odds_state='MISSING') AS payout_odds_missing_count,
                COUNT(*) FILTER (WHERE movement_state='MOVED_AFTER_EVENT') AS moved_after_event_count,
                COUNT(*) FILTER (WHERE movement_state='NO_CLEAR_MOVE') AS no_clear_move_count,
                COUNT(*) FILTER (WHERE movement_state='ALREADY_MOVED_BEFORE_EVENT') AS already_moved_before_event_count,
                COUNT(*) FILTER (WHERE already_priced_in_state='YES') AS already_priced_in_yes_count,
                COUNT(*) FILTER (WHERE already_priced_in_state='NO') AS already_priced_in_no_count,
                COUNT(*) FILTER (WHERE already_priced_in_state='UNKNOWN') AS already_priced_in_unknown_count,
                COUNT(*) FILTER (WHERE eligible_for_candidate_generation_later IS TRUE) AS candidate_generation_later_eligible_count
            FROM targeted_market_revalidations
            """
        ).fetchone()
        skipped = conn.execute(
            """
            SELECT COALESCE(skip_reason, failure_reason, 'NONE') AS reason, COUNT(*) AS count
            FROM targeted_market_revalidations
            WHERE revalidation_state='SKIPPED'
            GROUP BY COALESCE(skip_reason, failure_reason, 'NONE')
            ORDER BY count DESC, reason
            """
        ).fetchall()
        out = {key: int(value or 0) if isinstance(value, int) or key.endswith("_count") or key == "total_revalidation_rows" else value for key, value in dict(row).items()}
        out["eligible_links_seen"] = eligible
        out["skipped_count_by_reason"] = {str(item["reason"]): int(item["count"] or 0) for item in skipped}
        if _table_exists(conn, "proactive_candidate_seeds"):
            seed_row = conn.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE seed_state='GENERATED') AS generated_seed_count,
                    COUNT(*) FILTER (WHERE seed_state='WATCH_ONLY') AS watch_only_seed_count,
                    COUNT(*) FILTER (WHERE mesh_handoff_state='SENT_DATA_ONLY') AS mesh_handoff_sent_count,
                    COUNT(*) FILTER (WHERE mesh_handoff_state='SKIPPED') AS mesh_handoff_skipped_count
                FROM proactive_candidate_seeds
                """
            ).fetchone()
            out["generated_seed_count"] = int((seed_row or {}).get("generated_seed_count") or 0)
            out["watch_only_seed_count"] = int((seed_row or {}).get("watch_only_seed_count") or 0)
            out["mesh_handoff_sent_count"] = int((seed_row or {}).get("mesh_handoff_sent_count") or 0)
            out["mesh_handoff_skipped_count"] = int((seed_row or {}).get("mesh_handoff_skipped_count") or 0)
        else:
            out["generated_seed_count"] = 0
            out["watch_only_seed_count"] = 0
            out["mesh_handoff_sent_count"] = 0
            out["mesh_handoff_skipped_count"] = 0
        if _table_exists(conn, "research_priority_watchlist"):
            priority = conn.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE rpw.scheduler_state='DUE') AS revalidated_due_market_count,
                    COUNT(*) FILTER (WHERE rpw.priority_band='HIGH') AS revalidated_high_priority_count
                FROM targeted_market_revalidations tmr
                JOIN research_priority_watchlist rpw ON rpw.market_id=tmr.market_id
                """
            ).fetchone()
            out["revalidated_due_market_count"] = int((priority or {}).get("revalidated_due_market_count") or 0)
            out["revalidated_high_priority_count"] = int((priority or {}).get("revalidated_high_priority_count") or 0)
        else:
            out["revalidated_due_market_count"] = 0
            out["revalidated_high_priority_count"] = 0
        return out

    def _latest_refresh_run(self, conn: Any) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM targeted_market_revalidation_refresh_runs
            ORDER BY completed_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ).fetchone()
        return _jsonable(dict(row)) if row else None

    def _sample(self, conn: Any, where: str, *, limit: int) -> list[dict[str, Any]]:
        if _table_exists(conn, "proactive_candidate_seeds"):
            seed_select = """
                   seed.generated_seed_count,
                   seed.watch_only_seed_count,
                   seed.latest_seed_id,
                   seed.mesh_handoff_state
            """
            seed_join = """
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) FILTER (WHERE seed_state='GENERATED') AS generated_seed_count,
                    COUNT(*) FILTER (WHERE seed_state='WATCH_ONLY') AS watch_only_seed_count,
                    (ARRAY_AGG(proactive_candidate_seed_id ORDER BY updated_at DESC, id DESC))[1] AS latest_seed_id,
                    (ARRAY_AGG(mesh_handoff_state ORDER BY updated_at DESC, id DESC))[1] AS mesh_handoff_state
                FROM proactive_candidate_seeds pcs
                WHERE pcs.targeted_revalidation_id=tmr.targeted_revalidation_id
                   OR pcs.market_id=tmr.market_id
            ) seed ON true
            """
        else:
            seed_select = """
                   0::integer AS generated_seed_count,
                   0::integer AS watch_only_seed_count,
                   NULL::text AS latest_seed_id,
                   NULL::text AS mesh_handoff_state
            """
            seed_join = ""
        if _table_exists(conn, "research_priority_watchlist"):
            priority_select = """
                   rpw.priority_band AS watchlist_priority_band,
                   rpw.priority_score AS watchlist_priority_score,
                   rpw.scheduler_state AS watchlist_scheduler_state
            """
            priority_join = """
            LEFT JOIN LATERAL (
                SELECT priority_band, priority_score, scheduler_state
                FROM research_priority_watchlist rpw
                WHERE rpw.market_id=tmr.market_id
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
            ) rpw ON true
            """
        else:
            priority_select = """
                   NULL::text AS watchlist_priority_band,
                   NULL::numeric AS watchlist_priority_score,
                   NULL::text AS watchlist_scheduler_state
            """
            priority_join = ""
        rows = conn.execute(
            f"""
            SELECT tmr.*,
                   {seed_select},
                   {priority_select}
            FROM targeted_market_revalidations tmr
            {seed_join}
            {priority_join}
            WHERE {where}
            ORDER BY tmr.link_confidence DESC, tmr.updated_at DESC, tmr.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _ensure_tables(self, conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS targeted_market_revalidations (
                id BIGSERIAL PRIMARY KEY,
                targeted_revalidation_id TEXT NOT NULL UNIQUE,
                refresh_run_id TEXT,
                source_event_id TEXT NOT NULL,
                event_to_market_link_id TEXT NOT NULL,
                market_memory_id TEXT,
                market_id TEXT,
                condition_id TEXT,
                link_type TEXT NOT NULL,
                link_confidence NUMERIC NOT NULL DEFAULT 0,
                revalidation_state TEXT NOT NULL DEFAULT 'SKIPPED',
                skip_reason TEXT,
                failure_reason TEXT,
                market_identity_state TEXT NOT NULL DEFAULT 'UNRESOLVED',
                token_verification_state TEXT NOT NULL DEFAULT 'TOKENS_MISSING',
                token_side_resolution_state TEXT NOT NULL DEFAULT 'TOKEN_SIDE_UNKNOWN',
                metadata_refresh_state TEXT NOT NULL DEFAULT 'NOT_AVAILABLE',
                orderbook_refresh_state TEXT NOT NULL DEFAULT 'NOT_AVAILABLE',
                selected_orderbook_snapshot_id TEXT,
                liquidity_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                spread_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                payout_odds_state TEXT NOT NULL DEFAULT 'MISSING',
                movement_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                signal_state TEXT NOT NULL DEFAULT 'MISSING',
                candidate_event_scope_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                already_priced_in_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                already_priced_in_reason TEXT,
                eligible_for_candidate_generation_later BOOLEAN NOT NULL DEFAULT FALSE,
                candidate_generation_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS targeted_market_revalidation_refresh_runs (
                id BIGSERIAL PRIMARY KEY,
                refresh_run_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                eligible_links_seen INTEGER NOT NULL DEFAULT 0,
                links_revalidated INTEGER NOT NULL DEFAULT 0,
                links_skipped INTEGER NOT NULL DEFAULT 0,
                links_failed INTEGER NOT NULL DEFAULT 0,
                links_partial INTEGER NOT NULL DEFAULT 0,
                markets_refreshed INTEGER NOT NULL DEFAULT 0,
                latest_error TEXT,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def _market_memory_row(conn: Any, link: dict[str, Any]) -> dict[str, Any] | None:
    if not _table_exists(conn, "market_universe_memory"):
        return None
    row = conn.execute(
        """
        SELECT *
        FROM market_universe_memory
        WHERE (market_memory_id IS NOT DISTINCT FROM %s)
           OR (market_id IS NOT DISTINCT FROM %s)
           OR (condition_id IS NOT DISTINCT FROM %s)
        ORDER BY
            CASE WHEN market_memory_id IS NOT DISTINCT FROM %s THEN 0 ELSE 1 END,
            updated_at DESC NULLS LAST,
            id DESC
        LIMIT 1
        """,
        (
            link.get("market_memory_id"),
            link.get("market_id"),
            link.get("condition_id"),
            link.get("market_memory_id"),
        ),
    ).fetchone()
    return dict(row) if row else None


def _latest_orderbook(conn: Any, market: dict[str, Any], *, token_side_state: str, direction: str) -> dict[str, Any]:
    if not _table_exists(conn, "orderbook_snapshots"):
        return {"orderbook_refresh_state": "NOT_AVAILABLE", "selected_orderbook_snapshot_id": None, "liquidity_state": "UNKNOWN", "spread_state": "UNKNOWN"}
    columns = _columns(conn, "orderbook_snapshots")
    time_expr = _coalesce_expr(columns, ["collected_at", "snapshot_at", "created_at"])
    side = _side_for_orderbook(token_side_state, direction)
    token = market.get("yes_token_id") if side == "YES" else market.get("no_token_id") if side == "NO" else None
    token_filter = "AND token_id=%s" if token else ""
    params: list[Any] = [market.get("market_id")]
    if token:
        params.append(token)
    row = conn.execute(
        f"""
        SELECT *
        FROM orderbook_snapshots
        WHERE market_id=%s
          {token_filter}
        ORDER BY {time_expr} DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    if not row:
        return {"orderbook_refresh_state": "FAILED", "selected_orderbook_snapshot_id": None, "liquidity_state": "UNKNOWN", "spread_state": "UNKNOWN"}
    item = dict(row)
    observed_at = _first_dt(item.get("collected_at"), item.get("snapshot_at"), item.get("created_at"))
    age = _age_seconds(observed_at)
    stale_flag = bool(item.get("is_stale")) or str(item.get("snapshot_status") or "").upper() in {"STALE", "FAILED"}
    state = "STALE" if stale_flag or (age is not None and age > ORDERBOOK_TTL_SECONDS) else "FRESH"
    spread = _to_float(item.get("spread"))
    liquidity = _to_float(item.get("liquidity_score"))
    if liquidity is None:
        depth = sum(_to_float(item.get(name)) or 0.0 for name in ("depth_1c", "depth_2c", "depth_5c"))
        liquidity = min(depth, 1.0) if depth > 0 else None
    return {
        "orderbook_refresh_state": state,
        "selected_orderbook_snapshot_id": str(item.get("orderbook_snapshot_id") or item.get("snapshot_id") or item.get("id")),
        "liquidity_state": _liquidity_state(liquidity),
        "spread_state": _spread_state(spread),
        "observed_at": _iso(observed_at),
        "age_seconds": age,
        "side_checked": side or "MARKET_LEVEL",
        "token_checked": token,
        "spread": spread,
        "liquidity_score": liquidity,
    }


def _latest_payout(conn: Any, market_id: str | None) -> dict[str, Any]:
    if not market_id or not _table_exists(conn, "payout_odds_evaluations"):
        return {"payout_odds_state": "MISSING"}
    row = conn.execute(
        """
        SELECT *
        FROM payout_odds_evaluations
        WHERE market_id=%s
        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        (market_id,),
    ).fetchone()
    if not row:
        return {"payout_odds_state": "MISSING"}
    item = dict(row)
    ts = _first_dt(item.get("updated_at"), item.get("created_at"))
    age = _age_seconds(ts)
    return {
        "payout_odds_state": "STALE" if age is not None and age > 86400 else "AVAILABLE",
        "evaluation_id": item.get("evaluation_id"),
        "updated_at": _iso(ts),
    }


def _movement_state(conn: Any, market_id: str | None, event_ts: Any) -> dict[str, Any]:
    if not market_id or not event_ts or not _table_exists(conn, "market_technical_signals"):
        return {"movement_state": "UNKNOWN", "reason": "MARKET_OR_EVENT_TIMESTAMP_MISSING"}
    event_dt = _as_dt(event_ts)
    after = conn.execute(
        """
        SELECT *
        FROM market_technical_signals
        WHERE market_id=%s AND ts >= %s
        ORDER BY ts ASC, id ASC
        LIMIT 1
        """,
        (market_id, event_dt),
    ).fetchone()
    before = conn.execute(
        """
        SELECT *
        FROM market_technical_signals
        WHERE market_id=%s AND ts < %s
        ORDER BY ts DESC, id DESC
        LIMIT 1
        """,
        (market_id, event_dt),
    ).fetchone()
    if after and _movement_strength(dict(after)) >= 0.10:
        return {"movement_state": "MOVED_AFTER_EVENT", "signal_id": dict(after).get("id"), "reason": "Technical signal moved after event timestamp."}
    if before and _movement_strength(dict(before)) >= 0.10:
        return {"movement_state": "ALREADY_MOVED_BEFORE_EVENT", "signal_id": dict(before).get("id"), "reason": "Market movement existed before event timestamp."}
    if after or before:
        return {"movement_state": "NO_CLEAR_MOVE", "reason": "Signals exist but no material movement threshold was met."}
    return {"movement_state": "UNKNOWN", "reason": "No market movement signals exist for this market."}


def _signal_state(conn: Any, market_id: str | None) -> str:
    if not market_id:
        return "MISSING"
    latest: datetime | None = None
    for table in ("orderbook_signals", "market_technical_signals"):
        if not _table_exists(conn, table):
            continue
        col = "ts" if "ts" in _columns(conn, table) else "created_at"
        row = conn.execute(f"SELECT {col} AS ts FROM {table} WHERE market_id=%s ORDER BY {col} DESC NULLS LAST, id DESC LIMIT 1", (market_id,)).fetchone()
        latest = _max_dt(latest, (row or {}).get("ts") if row else None)
    if not latest:
        return "MISSING"
    age = _age_seconds(latest)
    return "STALE" if age is not None and age > 900 else "AVAILABLE"


def _candidate_generation_blockers(
    *,
    market: dict[str, Any],
    identity_state: str,
    token_state: str,
    token_side_state: str,
    orderbook_state: str,
    liquidity_state: str,
    link: dict[str, Any],
    candidate_scope: str,
    already_priced_in: str,
) -> list[str]:
    blockers: list[str] = []
    if str(link.get("link_type")) not in ELIGIBLE_LINK_TYPES:
        blockers.append("LINK_NOT_ELIGIBLE")
    if str(link.get("candidate_actionability_hint")) != "REVALIDATION_ELIGIBLE":
        blockers.append("LINK_HINT_NOT_REVALIDATION_ELIGIBLE")
    if identity_state != "VERIFIED":
        blockers.append("MARKET_IDENTITY_NOT_VERIFIED")
    if token_state != "TOKENS_VERIFIED":
        blockers.append("TOKENS_NOT_VERIFIED")
    if token_side_state == "TOKEN_SIDE_CONFLICT":
        blockers.append("TOKEN_SIDE_CONFLICT")
    if token_side_state not in TOKEN_SIDE_CANDIDATE_SCOPED:
        blockers.append("TOKEN_SIDE_NOT_CANDIDATE_ACTIONABLE")
    if str(market.get("status") or "").upper() not in {"ACTIVE", "STALE"}:
        blockers.append("MARKET_NOT_ACTIVE")
    if orderbook_state != "FRESH":
        blockers.append("ORDERBOOK_NOT_FRESH")
    if liquidity_state in {"UNKNOWN", "POOR"}:
        blockers.append("LIQUIDITY_NOT_USABLE")
    if candidate_scope != "CANDIDATE_SCOPED":
        blockers.append("CANDIDATE_EVENT_SCOPE_NOT_VERIFIED")
    if already_priced_in == "YES":
        blockers.append("EVENT_ALREADY_PRICED_IN")
    return _unique(blockers)


def _skip_reason(link: dict[str, Any]) -> str:
    link_type = str(link.get("link_type") or "UNKNOWN")
    hint = str(link.get("candidate_actionability_hint") or "NOT_RELEVANT")
    confidence = _to_float(link.get("link_confidence")) or 0.0
    if link_type in SKIPPED_LINK_TYPES:
        return f"{link_type}_NOT_REVALIDATED_BY_STAGE3_POLICY"
    if hint in SKIPPED_HINTS:
        return f"{hint}_NOT_REVALIDATED_BY_STAGE3_POLICY"
    if link_type == "LIKELY_LINK" and confidence < LIKELY_CONFIDENCE_THRESHOLD:
        return "LIKELY_LINK_BELOW_REVALIDATION_THRESHOLD"
    return "NOT_REVALIDATION_ELIGIBLE"


def _candidate_event_scope_state(token_side_state: str, token_state: str) -> str:
    if token_side_state == "TOKEN_SIDE_CONFLICT" or token_state == "TOKENS_MISMATCH":
        return "NOT_ACTIONABLE"
    if token_side_state in TOKEN_SIDE_CANDIDATE_SCOPED and token_state == "TOKENS_VERIFIED":
        return "CANDIDATE_SCOPED"
    if token_side_state in TOKEN_SIDE_MARKET_LEVEL:
        return "MARKET_LEVEL_ONLY"
    return "UNKNOWN"


def _already_priced_in_state(link: dict[str, Any], movement: dict[str, Any]) -> tuple[str, str]:
    existing = str(link.get("event_already_priced_in_state") or "").upper()
    if existing in {"YES", "NO"}:
        return existing, "Source Event Memory already evaluated this event."
    movement_state = movement.get("movement_state")
    if movement_state == "ALREADY_MOVED_BEFORE_EVENT":
        return "YES", "Market movement existed before the recalled source event."
    if movement_state == "NO_CLEAR_MOVE":
        return "NO", "No clear market movement was detected around the source event."
    return "UNKNOWN", movement.get("reason") or "Insufficient movement evidence for already-priced-in classification."


def _identity_state(market: dict[str, Any]) -> str:
    state = str(market.get("identity_verification_state") or "UNRESOLVED")
    if state in {"VERIFIED", "PARTIAL", "UNRESOLVED", "CONFLICT"}:
        return state
    return "VERIFIED" if market.get("market_id") and market.get("condition_id") else "PARTIAL" if market.get("market_id") or market.get("condition_id") else "UNRESOLVED"


def _metadata_state(market: dict[str, Any]) -> str:
    freshness = str(market.get("freshness_state") or "").upper()
    if freshness == "FRESH":
        return "FRESH"
    if freshness in {"STALE", "NEEDS_REFRESH"}:
        return "STALE"
    return "NOT_AVAILABLE"


def _required_to_pass(blockers: list[str]) -> list[str]:
    mapping = {
        "MARKET_IDENTITY_NOT_VERIFIED": "Refresh Market Universe Memory until market_id and condition_id are verified.",
        "TOKENS_NOT_VERIFIED": "Verify YES/NO token identity before candidate generation.",
        "TOKEN_SIDE_CONFLICT": "Resolve token/side conflict before any candidate-level use.",
        "TOKEN_SIDE_NOT_CANDIDATE_ACTIONABLE": "Resolve directional side/token mapping for candidate generation.",
        "MARKET_NOT_ACTIVE": "Market must be active for candidate generation.",
        "ORDERBOOK_NOT_FRESH": "Refresh trusted orderbook for the linked market/token.",
        "LIQUIDITY_NOT_USABLE": "Collect usable liquidity/depth evidence.",
        "CANDIDATE_EVENT_SCOPE_NOT_VERIFIED": "Verify candidate-scoped event scope.",
        "EVENT_ALREADY_PRICED_IN": "Find remaining dislocation after event reaction.",
        "WEAK_LINK_NOT_REVALIDATED_BY_STAGE3_POLICY": "Upgrade recall to DIRECT_LINK or high-confidence LIKELY_LINK.",
        "CONTEXT_ONLY_NOT_REVALIDATED_BY_STAGE3_POLICY": "Context links are memory-only and require stronger market-specific evidence.",
        "NO_LINK_NOT_REVALIDATED_BY_STAGE3_POLICY": "No meaningful market relation exists.",
        "WATCH_ONLY_NOT_REVALIDATED_BY_STAGE3_POLICY": "Observation-only recall needs stronger confidence and token/side resolution.",
        "BLOCKED_BY_LOW_CONFIDENCE_NOT_REVALIDATED_BY_STAGE3_POLICY": "Increase link confidence above Stage 3 threshold.",
        "BLOCKED_BY_TOKEN_SIDE_UNKNOWN_NOT_REVALIDATED_BY_STAGE3_POLICY": "Resolve token/side before revalidation eligibility.",
        "BLOCKED_BY_CONFLICT_NOT_REVALIDATED_BY_STAGE3_POLICY": "Resolve linker conflict before revalidation eligibility.",
        "LIKELY_LINK_BELOW_REVALIDATION_THRESHOLD": "Likely link must meet the configured revalidation threshold.",
    }
    return _unique([mapping.get(blocker, f"Resolve {blocker}.") for blocker in blockers])


def _side_for_orderbook(token_side_state: str, direction: str) -> str | None:
    if token_side_state == "SIDE_DIRECTIONAL_YES" or direction == "YES":
        return "YES"
    if token_side_state == "SIDE_DIRECTIONAL_NO" or direction == "NO":
        return "NO"
    return None


def _liquidity_state(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value >= 0.6:
        return "GOOD"
    if value >= 0.25:
        return "MEDIUM"
    return "POOR"


def _spread_state(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value <= 0.02:
        return "TIGHT"
    if value <= 0.05:
        return "MEDIUM"
    return "WIDE"


def _movement_strength(row: dict[str, Any]) -> float:
    values = [
        abs(_to_float(row.get("momentum_score")) or 0.0),
        abs(_to_float(row.get("trend_strength")) or 0.0),
        abs(_to_float(row.get("price_change_15m")) or 0.0),
        abs(_to_float(row.get("price_change_1h")) or 0.0),
    ]
    return max(values or [0.0])


def _revalidation_id(recall_id: str, started_at: datetime) -> str:
    bucket = started_at.replace(minute=0, second=0, microsecond=0).isoformat()
    raw = f"{recall_id}|{bucket}"
    return f"targeted_revalidation_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:28]}"


def _empty_market_fields() -> dict[str, Any]:
    return {
        "targeted_revalidation_id": None,
        "latest_targeted_revalidation_state": "MISSING",
        "latest_targeted_revalidation_at": None,
        "orderbook_refresh_state_from_revalidation": "UNKNOWN",
        "refreshed_orderbook_snapshot_id": None,
        "movement_state_from_revalidation": "UNKNOWN",
        "already_priced_in_state_from_revalidation": "UNKNOWN",
        "revalidation_candidate_generation_later_state": "NOT_EVALUATED",
        "candidate_generation_later_eligible": False,
        "recent_revalidated_event_count": 0,
        "candidate_generation_later_eligible_count": 0,
        "downstream_seed_mesh_count": 0,
        "best_downstream_seed_score": None,
    }


def _empty_summary(status: str, now: datetime) -> dict[str, Any]:
    return {
        "status": status,
        "source": "targeted_market_revalidation",
        "last_updated": now.isoformat(),
        "freshness_state": "MISSING",
        "readiness_state": "UNKNOWN",
        "truth_state": "UNKNOWN",
        "counts": {},
        "latest_refresh": None,
        "top_revalidated_markets": [],
        "top_skipped_links": [],
        "top_failures": [],
        "warnings": ["Database unavailable."],
        "errors": [],
        "generated_at": now.isoformat(),
    }


def _safety_counts(conn: Any) -> dict[str, int]:
    tables = ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "positions", "shadow_orders")
    counts: dict[str, int] = {}
    for table in tables:
        if _table_exists(conn, table):
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
            counts[table] = int((row or {}).get("count") or 0)
        else:
            counts[table] = 0
    return counts


def _trading_mutation(before: dict[str, int], after: dict[str, int]) -> bool:
    return any(int(after.get(key, 0)) != int(before.get(key, 0)) for key in set(before) | set(after))


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
    return bool(row and row["name"])


def _columns(conn: Any, table: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = ANY(current_schemas(false))
          AND table_name=%s
        """,
        (table,),
    ).fetchall()
    return {str(row["column_name"]) for row in rows}


def _coalesce_expr(columns: set[str], names: list[str]) -> str:
    available = [name for name in names if name in columns]
    if not available:
        return "id"
    return "COALESCE(" + ", ".join(available) + ")"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _first_dt(*values: Any) -> datetime | None:
    for value in values:
        if value:
            return _as_dt(value)
    return None


def _max_dt(*values: Any) -> datetime | None:
    items = [_as_dt(value) for value in values if value]
    return max(items) if items else None


def _age_seconds(value: datetime | None) -> int | None:
    if not value:
        return None
    return max(0, int((datetime.now(UTC) - (value if value.tzinfo else value.replace(tzinfo=UTC))).total_seconds()))


def _iso(value: Any) -> str | None:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if value is not None else None


def _unique(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
