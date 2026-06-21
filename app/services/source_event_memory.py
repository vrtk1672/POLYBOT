from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory


RECENT_WINDOW_HOURS = 72
MAX_EVENTS_PER_REFRESH = 500
MAX_LINKS_PER_EVENT = 10
REFRESH_INTERVAL_SECONDS = 900

SOURCE_TYPES = {
    "NEWS",
    "RSS",
    "CRYPTOPANIC",
    "WHALE",
    "WALLET_FLOW",
    "ORDERBOOK_MOVEMENT",
    "MARKET_MOVEMENT",
    "SIGNAL",
    "PAYOUT_ODDS",
    "AI_SUMMARY",
    "UNKNOWN",
}

LINK_TYPES = ("DIRECT_LINK", "LIKELY_LINK", "WEAK_LINK", "CONTEXT_ONLY", "NO_LINK")

TOKEN_SIDE_STATES = {
    "TOKEN_SIDE_DIRECT",
    "MARKET_LEVEL_ONLY",
    "TOKEN_SIDE_UNKNOWN",
    "TOKEN_SIDE_CONFLICT",
    "SIDE_DIRECTIONAL_YES",
    "SIDE_DIRECTIONAL_NO",
    "SIDE_DIRECTIONAL_NEUTRAL",
    "SIDE_DIRECTIONAL_MIXED",
}

ACTIONABILITY_HINTS = {
    "REVALIDATION_ELIGIBLE",
    "WATCH_ONLY",
    "CONTEXT_ONLY",
    "NOT_RELEVANT",
    "BLOCKED_BY_LOW_CONFIDENCE",
    "BLOCKED_BY_TOKEN_SIDE_UNKNOWN",
    "BLOCKED_BY_CONFLICT",
}

ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    "bitcoin": ("bitcoin", "btc", "xbt"),
    "ethereum": ("ethereum", "ether", "eth"),
    "sec": ("sec", "securities and exchange commission"),
    "etf": ("etf", "etfs", "exchange traded fund", "exchange-traded fund"),
    "spot etf": ("spot etf", "spot bitcoin etf", "spot ethereum etf"),
    "crypto regulation": ("crypto regulation", "cryptocurrency regulation", "digital asset regulation"),
    "federal reserve": ("fed", "federal reserve", "fomc", "federal open market committee"),
    "inflation": ("cpi", "inflation", "consumer price index"),
    "donald trump": ("trump", "donald trump"),
    "joe biden": ("biden", "joe biden"),
    "united states": ("us", "usa", "u.s.", "united states", "america"),
    "artificial intelligence": ("ai", "artificial intelligence"),
}

GENERIC_LINK_TERMS = {
    "market",
    "markets",
    "prediction",
    "polymarket",
    "event",
    "update",
    "signal",
    "source",
    "status",
    "observed",
    "yes",
    "no",
}


class SourceEventMemoryService:
    """DATA_ONLY source event memory and event-to-market recall.

    The service normalizes existing source rows into canonical event memory and
    links them to Stage 1 market universe memory. It never creates execution
    candidates, paper artifacts, live artifacts, or trade approvals.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def refresh_events(
        self,
        *,
        force: bool = False,
        window_hours: int = RECENT_WINDOW_HOURS,
        max_events: int = MAX_EVENTS_PER_REFRESH,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"source_event_memory_refresh_{uuid4().hex}"
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "refresh_run_id": run_id, "events_seen": 0}
        with self._factory.connect() as conn, conn.transaction():
            self._ensure_tables(conn)
            if not force and self._recent_success_exists(conn, min_interval_seconds=REFRESH_INTERVAL_SECONDS):
                latest = self._latest_refresh_run(conn)
                return {
                    "status": "SKIPPED_RECENT",
                    "refresh_run_id": latest.get("refresh_run_id") if latest else run_id,
                    "latest_refresh": _jsonable(latest),
                    "required_to_pass": [f"Wait {REFRESH_INTERVAL_SECONDS}s between event-memory refreshes or pass force=true."],
                }
            safety_before = _safety_counts(conn)
            source_rows = self._source_rows(conn, window_hours=window_hours, limit=max_events)
            markets = self._market_rows(conn)
            stats = {
                "events_seen": 0,
                "events_new": 0,
                "events_updated": 0,
                "duplicate_events": 0,
                "links_created": 0,
                "links_updated": 0,
                "unlinked_events": 0,
                "errors_count": 0,
            }
            errors: list[str] = []
            for source_row in source_rows:
                try:
                    event = _normalize_event(source_row, now=started_at)
                    existing = self._existing_event(conn, event["dedupe_key"])
                    created = existing is None
                    self._upsert_event(conn, event)
                    links = self._build_links(event, markets)
                    if not any(link["link_type"] != "NO_LINK" for link in links):
                        stats["unlinked_events"] += 1
                    for link in links:
                        link_existing = self._existing_link(conn, link["recall_id"])
                        self._upsert_link(conn, link)
                        stats["links_created"] += int(link_existing is None)
                        stats["links_updated"] += int(link_existing is not None)
                    self._update_event_link_summary(conn, event["source_event_id"])
                    stats["events_seen"] += 1
                    stats["events_new"] += int(created)
                    stats["events_updated"] += int(not created)
                    stats["duplicate_events"] += int(not created)
                except Exception as exc:
                    stats["errors_count"] += 1
                    errors.append(f"{type(exc).__name__}: {exc}")
            safety_after = _safety_counts(conn)
            status = "OK" if not errors else "PARTIAL" if stats["events_seen"] else "ERROR"
            completed_at = datetime.now(UTC)
            self._insert_refresh_run(
                conn,
                refresh_run_id=run_id,
                refresh_type="SOURCE_EVENT_MEMORY_REFRESH",
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                latest_error=errors[0] if errors else None,
                **stats,
                metadata={
                    "window_hours": window_hours,
                    "max_events": max_events,
                    "source_tables": sorted({row["source_table"] for row in source_rows}),
                    "market_memory_rows": len(markets),
                    "safety_before": safety_before,
                    "safety_after": safety_after,
                    "trading_mutation": _trading_mutation(safety_before, safety_after),
                    "targeted_revalidation_triggered": False,
                    "execution_candidates_created": False,
                    "errors": errors[:5],
                },
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
            top_linked = self._sample_events(conn, "top_link_confidence > 0", limit=limit)
            unlinked = self._sample_events(conn, "top_link_confidence = 0", limit=limit)
            direct = self._sample_links(conn, "link_type='DIRECT_LINK'", limit=limit)
            likely = self._sample_links(conn, "link_type='LIKELY_LINK'", limit=limit)
        return {
            "status": "REAL" if counts["total_source_events"] else "MISSING",
            "source": "source_event_memory + event_to_market_recall",
            "last_updated": (latest or {}).get("completed_at") or now.isoformat(),
            "freshness_state": "FRESH" if latest and counts["total_source_events"] else "MISSING",
            "readiness_state": "READY" if counts["total_source_events"] else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if counts["total_source_events"] else "UNKNOWN",
            "counts": counts,
            "latest_refresh": _jsonable(latest),
            "sample_top_linked_events": top_linked,
            "sample_unlinked_events": unlinked,
            "sample_direct_links": direct,
            "sample_likely_links": likely,
            "warnings": [] if counts["total_source_events"] else ["Source event memory has not been refreshed yet."],
            "errors": [],
            "generated_at": now.isoformat(),
        }

    def recall(self, *, source_event_id: str) -> dict[str, Any]:
        if not source_event_id:
            return {"status": "BLOCKED", "blocker": "SOURCE_EVENT_ID_REQUIRED"}
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "event": None, "linked_markets": []}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            event = conn.execute("SELECT * FROM source_event_memory WHERE source_event_id=%s LIMIT 1", (source_event_id,)).fetchone()
            links = conn.execute(
                """
                SELECT *
                FROM event_to_market_recall
                WHERE source_event_id=%s
                ORDER BY link_confidence DESC, updated_at DESC, id DESC
                """,
                (source_event_id,),
            ).fetchall()
        return {
            "status": "FOUND" if event else "NOT_FOUND",
            "source_event": _jsonable(dict(event)) if event else None,
            "linked_markets": [_jsonable(dict(row)) for row in links],
        }

    def by_market(self, *, market_id: str, limit: int = 20) -> dict[str, Any]:
        if not market_id:
            return {"status": "BLOCKED", "blocker": "MARKET_ID_REQUIRED"}
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "events": []}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            rows = conn.execute(
                """
                SELECT sem.*, emr.recall_id, emr.market_id AS linked_market_id,
                       emr.market_memory_id AS linked_market_memory_id,
                       emr.condition_id AS linked_condition_id,
                       emr.link_type, emr.link_confidence,
                       emr.matched_aliases_json, emr.matched_fields_json,
                       emr.confidence_components_json, emr.semantic_score,
                       emr.token_side_resolution_state, emr.candidate_actionability_hint,
                       emr.guardrail_reason,
                       emr.direction_for_market, emr.reason, emr.eligible_for_targeted_revalidation
                FROM event_to_market_recall emr
                JOIN source_event_memory sem ON sem.source_event_id=emr.source_event_id
                WHERE emr.market_id=%s
                ORDER BY emr.link_confidence DESC, sem.event_timestamp DESC NULLS LAST, sem.updated_at DESC
                LIMIT %s
                """,
                (market_id, limit),
            ).fetchall()
        return {"status": "REAL", "market_id": market_id, "events": [_jsonable(dict(row)) for row in rows]}

    def linker_diagnostics(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "thresholds": _linker_thresholds(), "alias_count": _alias_count()}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            guardrails = conn.execute(
                """
                SELECT candidate_actionability_hint, COUNT(*) AS count
                FROM event_to_market_recall
                GROUP BY candidate_actionability_hint
                ORDER BY candidate_actionability_hint
                """
            ).fetchall()
            token_side = conn.execute(
                """
                SELECT token_side_resolution_state, COUNT(*) AS count
                FROM event_to_market_recall
                GROUP BY token_side_resolution_state
                ORDER BY token_side_resolution_state
                """
            ).fetchall()
            top_aliases = conn.execute(
                """
                SELECT alias, COUNT(*) AS count
                FROM event_to_market_recall,
                     LATERAL jsonb_array_elements_text(matched_aliases_json) AS alias
                GROUP BY alias
                ORDER BY count DESC, alias
                LIMIT 20
                """
            ).fetchall()
        return {
            "status": "REAL",
            "thresholds": _linker_thresholds(),
            "alias_count": _alias_count(),
            "semantic_system_available": False,
            "semantic_method": "deterministic_token_jaccard",
            "false_positive_guardrail_counts": {str(row["candidate_actionability_hint"]): int(row["count"] or 0) for row in guardrails},
            "token_side_resolution_counts": {str(row["token_side_resolution_state"]): int(row["count"] or 0) for row in token_side},
            "top_aliases_matched": [{"alias": row["alias"], "count": int(row["count"] or 0)} for row in top_aliases],
            "stage3_execution_triggered": False,
            "execution_candidates_created": False,
        }

    def link_fields_for_market(self, *, market_id: str | None) -> dict[str, Any]:
        if not market_id or not self._factory.enabled:
            return _empty_link_fields()
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS recent_source_event_count,
                    COUNT(*) FILTER (WHERE link_type='DIRECT_LINK') AS direct_event_link_count,
                    COUNT(*) FILTER (WHERE link_type='LIKELY_LINK') AS likely_event_link_count,
                    MAX(link_confidence) AS strongest_event_link_confidence,
                    (ARRAY_AGG(link_type ORDER BY link_confidence DESC, updated_at DESC))[1] AS strongest_event_link_type,
                    (ARRAY_AGG(direction_for_market ORDER BY link_confidence DESC, updated_at DESC))[1] AS recent_directional_event_state,
                    (ARRAY_AGG(token_side_resolution_state ORDER BY link_confidence DESC, updated_at DESC))[1] AS token_side_resolution_state,
                    (ARRAY_AGG(candidate_actionability_hint ORDER BY link_confidence DESC, updated_at DESC))[1] AS event_link_actionability_hint,
                    (ARRAY_AGG(guardrail_reason ORDER BY link_confidence DESC, updated_at DESC))[1] AS event_link_guardrail_reason,
                    ARRAY_REMOVE(ARRAY_AGG(source_event_id ORDER BY link_confidence DESC, updated_at DESC), NULL) AS source_event_memory_ids,
                    ARRAY_REMOVE(ARRAY_AGG(recall_id ORDER BY link_confidence DESC, updated_at DESC), NULL) AS event_to_market_link_ids
                FROM event_to_market_recall
                WHERE market_id=%s
                  AND created_at >= now() - interval '72 hours'
                  AND link_type <> 'NO_LINK'
                """,
                (market_id,),
            ).fetchone()
        if not row or not int(row["recent_source_event_count"] or 0):
            return _empty_link_fields()
        direct = int(row["direct_event_link_count"] or 0)
        likely = int(row["likely_event_link_count"] or 0)
        strongest = row["strongest_event_link_type"]
        confidence = float(row["strongest_event_link_confidence"] or 0)
        try:
            from app.services.proactive_seed_mesh_inquiry import ProactiveSeedMeshInquiryService

            mesh_fields = ProactiveSeedMeshInquiryService(connection_factory=self._factory).fields_for_market(market_id=market_id)
        except Exception:
            mesh_fields = {"downstream_seed_mesh_count": 0, "downstream_edge_supported_count": 0}
        return {
            "recent_source_event_count": int(row["recent_source_event_count"] or 0),
            "strongest_event_link_type": strongest,
            "strongest_event_link_confidence": confidence,
            "recent_directional_event_state": row["recent_directional_event_state"] or "UNKNOWN",
            "recent_source_event_link_state": _link_state(strongest, confidence),
            "recall_link_state": _link_state(strongest, confidence),
            "event_link_actionability_hint": row["event_link_actionability_hint"] or "WATCH_ONLY",
            "token_side_resolution_state": row["token_side_resolution_state"] or "TOKEN_SIDE_UNKNOWN",
            "event_link_guardrail_reason": row["event_link_guardrail_reason"],
            "direct_event_link_count": direct,
            "likely_event_link_count": likely,
            "source_event_memory_ids": list(row["source_event_memory_ids"] or [])[:10],
            "event_to_market_link_ids": list(row["event_to_market_link_ids"] or [])[:10],
            "downstream_seed_mesh_count": mesh_fields.get("seed_mesh_inquiry_count", 0),
            "downstream_edge_supported_count": mesh_fields.get("downstream_edge_supported_count", 0),
        }

    def _source_rows(self, conn: Any, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        per_source_limit = max(10, limit // 8)
        rows.extend(self._news_rows(conn, window_hours=window_hours, limit=per_source_limit))
        rows.extend(self._external_rows(conn, window_hours=window_hours, limit=per_source_limit))
        rows.extend(self._whale_rows(conn, window_hours=window_hours, limit=per_source_limit))
        rows.extend(self._payout_rows(conn, window_hours=window_hours, limit=per_source_limit))
        rows.extend(self._movement_rows(conn, window_hours=window_hours, limit=per_source_limit))
        rows.extend(self._signal_rows(conn, window_hours=window_hours, limit=per_source_limit))
        rows.extend(self._ai_summary_rows(conn, window_hours=window_hours, limit=per_source_limit))
        rows.sort(key=lambda item: item.get("event_timestamp") or datetime.min.replace(tzinfo=UTC), reverse=True)
        return rows[:limit]

    def _news_rows(self, conn: Any, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "news_normalized_events"):
            return []
        source_join = "LEFT JOIN news_sources ns ON ns.source_id=n.source_id" if _table_exists(conn, "news_sources") else ""
        source_type_select = "ns.source_type" if _table_exists(conn, "news_sources") else "NULL::text"
        rows = conn.execute(
            f"""
            SELECT n.news_event_id::text AS source_record_id, n.news_event_id AS source_id,
                   n.source_id AS raw_source_id, n.url AS source_url,
                   COALESCE(n.event_time, n.published_at, n.collected_at, n.created_at) AS event_timestamp,
                   n.title AS headline, COALESCE(n.summary, n.normalized_text) AS summary,
                   n.entities_json, n.topics_json, n.category AS topic_class,
                   n.source_reliability AS event_confidence,
                   {source_type_select} AS raw_source_type,
                   l.market_id AS linked_market_id, l.direction AS link_direction,
                   l.confidence AS link_confidence, l.link_score AS link_score,
                   l.matched_entities_json AS link_entities, l.matched_terms_json AS link_terms,
                   i.already_priced_in AS already_priced_in_value,
                   i.strength AS direction_strength, i.reason AS source_reason
            FROM news_normalized_events n
            {source_join}
            LEFT JOIN LATERAL (
                SELECT *
                FROM news_market_links l
                WHERE l.news_event_id=n.news_event_id
                ORDER BY l.confidence DESC, l.link_score DESC, l.id DESC
                LIMIT 1
            ) l ON true
            LEFT JOIN LATERAL (
                SELECT *
                FROM news_impact_scores i
                WHERE i.news_event_id=n.news_event_id
                ORDER BY i.confidence DESC, i.strength DESC, i.id DESC
                LIMIT 1
            ) i ON true
            WHERE COALESCE(n.event_time, n.published_at, n.collected_at, n.created_at) >= now() - (%s || ' hours')::interval
            ORDER BY COALESCE(n.event_time, n.published_at, n.collected_at, n.created_at) DESC, n.id DESC
            LIMIT %s
            """,
            (window_hours, limit),
        ).fetchall()
        return [_event_seed(dict(row), source_table="news_normalized_events", source_type=_news_type(row.get("raw_source_type"), row.get("raw_source_id"))) for row in rows]

    def _external_rows(self, conn: Any, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "external_events_normalized"):
            return []
        enrich_join = """
            LEFT JOIN LATERAL (
                SELECT *
                FROM external_event_enrichments ee
                WHERE ee.external_event_id=e.id
                ORDER BY ee.created_at DESC
                LIMIT 1
            ) ee ON true
        """ if _table_exists(conn, "external_event_enrichments") else ""
        source_join = "LEFT JOIN intelligence_sources s ON s.id=e.intelligence_source_id" if _table_exists(conn, "intelligence_sources") else ""
        rows = conn.execute(
            f"""
            SELECT e.id::text AS source_record_id, e.id::text AS source_id,
                   e.canonical_url AS source_url, COALESCE(e.published_at, e.created_at) AS event_timestamp,
                   e.normalized_title AS headline, e.normalized_summary AS summary,
                   e.source_category AS topic_class, e.trust_weight_snapshot AS event_confidence,
                   e.metadata_json, e.canonical_hash AS raw_text_hash,
                   {'ee.entities_json' if _table_exists(conn, 'external_event_enrichments') else "'{}'::jsonb"} AS entities_json,
                   {'ee.topic_class' if _table_exists(conn, 'external_event_enrichments') else 'NULL::text'} AS enriched_topic_class,
                   {'ee.contradiction_hint_class' if _table_exists(conn, 'external_event_enrichments') else 'NULL::text'} AS contradiction_hint_class,
                   {'ee.usability_hint_class' if _table_exists(conn, 'external_event_enrichments') else 'NULL::text'} AS usability_hint_class,
                   {'s.source_type' if _table_exists(conn, 'intelligence_sources') else 'NULL::text'} AS raw_source_type,
                   {'s.source_key' if _table_exists(conn, 'intelligence_sources') else 'NULL::text'} AS raw_source_id
            FROM external_events_normalized e
            {enrich_join}
            {source_join}
            WHERE COALESCE(e.published_at, e.created_at) >= now() - (%s || ' hours')::interval
            ORDER BY COALESCE(e.published_at, e.created_at) DESC, e.created_at DESC
            LIMIT %s
            """,
            (window_hours, limit),
        ).fetchall()
        return [_event_seed(dict(row), source_table="external_events_normalized", source_type=_news_type(row.get("raw_source_type"), row.get("raw_source_id"))) for row in rows]

    def _whale_rows(self, conn: Any, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "whale_events"):
            return []
        rows = conn.execute(
            """
            SELECT COALESCE(whale_event_id, id::text) AS source_record_id,
                   COALESCE(source_id, source_type, 'whale') AS source_id,
                   COALESCE(event_time, event_timestamp, created_at) AS event_timestamp,
                   market_id AS linked_market_id, side AS link_direction,
                   confidence AS event_confidence, confidence AS link_confidence,
                   CONCAT('Whale ', COALESCE(action_type, event_classification, 'activity'), ' on market ', COALESCE(market_id, 'unknown')) AS headline,
                   detection_reason_text AS summary,
                   raw_event_json, normalized_event_json, wallet_address, whale_id,
                   COALESCE(event_classification, event_direction_class) AS raw_direction
            FROM whale_events
            WHERE COALESCE(event_time, event_timestamp, created_at) >= now() - (%s || ' hours')::interval
            ORDER BY COALESCE(event_time, event_timestamp, created_at) DESC, id DESC
            LIMIT %s
            """,
            (window_hours, limit),
        ).fetchall()
        return [_event_seed(dict(row), source_table="whale_events", source_type="WHALE") for row in rows]

    def _payout_rows(self, conn: Any, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "payout_odds_evaluations"):
            return []
        rows = conn.execute(
            """
            SELECT evaluation_id AS source_record_id, evaluation_id AS source_id,
                   updated_at AS event_timestamp, market_id AS linked_market_id,
                   side AS link_direction, token_id, condition_id,
                   CONCAT('Payout odds evaluation ', evaluation_id) AS headline,
                   CONCAT('price=', COALESCE(price::text, 'unknown'), ', profit_if_win=', COALESCE(profit_if_win::text, 'unknown')) AS summary,
                   CASE WHEN side IN ('YES','NO') THEN side ELSE 'UNKNOWN' END AS raw_direction,
                   CASE WHEN expected_value IS NOT NULL THEN 0.7 ELSE 0.45 END AS event_confidence,
                   CASE WHEN market_id IS NOT NULL THEN 0.84 ELSE 0 END AS link_confidence,
                   source_refs_json, metadata_json
            FROM payout_odds_evaluations
            WHERE updated_at >= now() - (%s || ' hours')::interval
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (window_hours, limit),
        ).fetchall()
        return [_event_seed(dict(row), source_table="payout_odds_evaluations", source_type="PAYOUT_ODDS") for row in rows]

    def _movement_rows(self, conn: Any, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if _table_exists(conn, "orderbook_signals"):
            book_rows = conn.execute(
                """
                SELECT id::text AS source_record_id, 'orderbook_signals' AS source_id,
                       ts AS event_timestamp, market_id AS linked_market_id, side AS link_direction, token_id,
                       CONCAT('Orderbook movement ', market_id, ' ', COALESCE(side, 'UNKNOWN')) AS headline,
                       CONCAT('spread_bps=', COALESCE(spread_bps::text, 'unknown'), ', imbalance=', COALESCE(imbalance_score::text, 'unknown')) AS summary,
                       CASE WHEN imbalance_score > 0 THEN 'YES' WHEN imbalance_score < 0 THEN 'NO' ELSE 'UNKNOWN' END AS raw_direction,
                       orderbook_quality_score AS event_confidence,
                       CASE WHEN market_id IS NOT NULL AND token_id IS NOT NULL THEN 0.74 ELSE 0 END AS link_confidence,
                       raw_orderbook_json
                FROM orderbook_signals
                WHERE ts >= now() - (%s || ' hours')::interval
                ORDER BY ts DESC, id DESC
                LIMIT %s
                """,
                (window_hours, max(1, limit // 2)),
            ).fetchall()
            rows.extend(_event_seed(dict(row), source_table="orderbook_signals", source_type="ORDERBOOK_MOVEMENT") for row in book_rows)
        if _table_exists(conn, "market_technical_signals"):
            market_rows = conn.execute(
                """
                SELECT id::text AS source_record_id, 'market_technical_signals' AS source_id,
                       ts AS event_timestamp, market_id AS linked_market_id,
                       trend_direction AS raw_direction,
                       CONCAT('Market movement ', market_id) AS headline,
                       CONCAT('momentum=', COALESCE(momentum_score::text, 'unknown'), ', trend=', COALESCE(trend_direction, 'unknown')) AS summary,
                       trend_strength AS event_confidence,
                       CASE WHEN market_id IS NOT NULL THEN 0.62 ELSE 0 END AS link_confidence,
                       raw_snapshot_json
                FROM market_technical_signals
                WHERE ts >= now() - (%s || ' hours')::interval
                ORDER BY ts DESC, id DESC
                LIMIT %s
                """,
                (window_hours, max(1, limit // 2)),
            ).fetchall()
            rows.extend(_event_seed(dict(row), source_table="market_technical_signals", source_type="MARKET_MOVEMENT") for row in market_rows)
        return rows

    def _signal_rows(self, conn: Any, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "neuron_signals"):
            return []
        rows = conn.execute(
            """
            SELECT signal_id AS source_record_id, COALESCE(source_name, neuron, 'neuron_signal') AS source_id,
                   created_at AS event_timestamp, market_id AS linked_market_id,
                   raw_direction, confidence AS event_confidence, confidence AS link_confidence,
                   CONCAT('Neuron signal ', COALESCE(neuron, 'unknown'), ' ', COALESCE(event_type, 'signal')) AS headline,
                   event_type AS summary, evidence_json, raw_payload_ref
            FROM neuron_signals
            WHERE created_at >= now() - (%s || ' hours')::interval
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (window_hours, limit),
        ).fetchall()
        return [_event_seed(dict(row), source_table="neuron_signals", source_type="SIGNAL") for row in rows]

    def _ai_summary_rows(self, conn: Any, *, window_hours: int, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "brain_outputs"):
            return []
        rows = conn.execute(
            """
            SELECT brain_output_id AS source_record_id, COALESCE(brain, generated_by, 'brain_output') AS source_id,
                   created_at AS event_timestamp, market_id AS linked_market_id,
                   recommendation AS raw_direction, confidence AS event_confidence,
                   CONCAT('AI summary ', COALESCE(brain, 'brain'), ' ', COALESCE(output_type, 'output')) AS headline,
                   reasoning_summary AS summary, metadata_json
            FROM brain_outputs
            WHERE created_at >= now() - (%s || ' hours')::interval
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (window_hours, limit),
        ).fetchall()
        return [_event_seed(dict(row), source_table="brain_outputs", source_type="AI_SUMMARY") for row in rows]

    def _market_rows(self, conn: Any) -> list[dict[str, Any]]:
        if not _table_exists(conn, "market_universe_memory"):
            return []
        rows = conn.execute(
            """
            SELECT market_memory_id, market_id, condition_id, slug, title, question,
                   tags_json, entities_json, keywords_json, category, status,
                   yes_token_id, no_token_id
            FROM market_universe_memory
            WHERE status IN ('ACTIVE','STALE','UNRESOLVED')
            ORDER BY research_priority, liquidity DESC NULLS LAST, volume DESC NULLS LAST
            LIMIT 500
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def _build_links(self, event: dict[str, Any], markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for market in markets:
            evidence = _link_evidence(event, market)
            link_type = _link_type(
                evidence["confidence"],
                direct=evidence["direct"],
                identifier=evidence["components"]["identifier_score"] >= 0.85,
                entity_topic=evidence["components"]["entity_score"] >= 0.24 and evidence["components"]["topic_score"] >= 0.14,
            )
            if link_type != "NO_LINK":
                candidates.append(
                    self._link_record(
                        event,
                        market,
                        link_type=link_type,
                        confidence=evidence["confidence"],
                        matched_entities=evidence["matched_entities"],
                        matched_topics=evidence["matched_topics"],
                        matched_keywords=evidence["matched_keywords"],
                        matched_aliases=evidence["matched_aliases"],
                        matched_fields=evidence["matched_fields"],
                        components=evidence["components"],
                        semantic_score=evidence["semantic_score"],
                        token_side_resolution_state=evidence["token_side_resolution_state"],
                    )
                )
        candidates.sort(key=lambda item: item["link_confidence"], reverse=True)
        if candidates:
            return candidates[:MAX_LINKS_PER_EVENT]
        return [self._no_link_record(event)]

    def _link_record(
        self,
        event: dict[str, Any],
        market: dict[str, Any],
        *,
        link_type: str,
        confidence: float,
        matched_entities: list[str],
        matched_topics: list[str],
        matched_keywords: list[str],
        matched_aliases: list[str],
        matched_fields: list[str],
        components: dict[str, Any],
        semantic_score: float,
        token_side_resolution_state: str,
    ) -> dict[str, Any]:
        direction = _direction(event.get("link_direction") or event.get("direction"))
        hint, eligible, guardrail = _actionability_hint(link_type, confidence, token_side_resolution_state, direction)
        reason = f"{link_type}: matched {', '.join(matched_fields) if matched_fields else 'source context'}; guardrail={guardrail}."
        return {
            "recall_id": _recall_id(event["source_event_id"], market.get("market_memory_id") or market.get("market_id"), link_type),
            "source_event_id": event["source_event_id"],
            "market_memory_id": market.get("market_memory_id"),
            "market_id": market.get("market_id"),
            "condition_id": market.get("condition_id"),
            "link_type": link_type,
            "link_confidence": confidence,
            "matched_entities_json": matched_entities,
            "matched_topics_json": matched_topics,
            "matched_keywords_json": matched_keywords,
            "matched_aliases_json": matched_aliases,
            "matched_fields_json": matched_fields,
            "confidence_components_json": components,
            "semantic_score": semantic_score,
            "token_side_resolution_state": token_side_resolution_state,
            "candidate_actionability_hint": hint,
            "guardrail_reason": guardrail,
            "direction_for_market": direction,
            "direction_confidence": float(event.get("direction_confidence") or 0),
            "eligible_for_targeted_revalidation": eligible,
            "reason": reason,
        }

    def _no_link_record(self, event: dict[str, Any]) -> dict[str, Any]:
        return {
            "recall_id": _recall_id(event["source_event_id"], "NO_MARKET", "NO_LINK"),
            "source_event_id": event["source_event_id"],
            "market_memory_id": None,
            "market_id": None,
            "condition_id": None,
            "link_type": "NO_LINK",
            "link_confidence": 0.0,
            "matched_entities_json": [],
            "matched_topics_json": [],
            "matched_keywords_json": [],
            "matched_aliases_json": [],
            "matched_fields_json": [],
            "confidence_components_json": _empty_components(),
            "semantic_score": 0.0,
            "token_side_resolution_state": "TOKEN_SIDE_UNKNOWN",
            "candidate_actionability_hint": "NOT_RELEVANT",
            "guardrail_reason": "NO_MARKET_RELATION",
            "direction_for_market": "UNKNOWN",
            "direction_confidence": 0.0,
            "eligible_for_targeted_revalidation": False,
            "reason": "No market universe memory row matched this event with usable confidence.",
        }

    def _upsert_event(self, conn: Any, event: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO source_event_memory (
                source_event_id, source_type, raw_source_type, source_id, source_table, source_record_id,
                source_url, event_timestamp, headline, summary, raw_text_hash, dedupe_key,
                entities_json, topics_json, keywords_json, direction, direction_confidence,
                event_confidence, freshness_seconds, already_priced_in_state,
                contradicts_previous_state, supports_existing_thesis_state, source_payload_json
            )
            VALUES (
                %(source_event_id)s, %(source_type)s, %(raw_source_type)s, %(source_id)s, %(source_table)s, %(source_record_id)s,
                %(source_url)s, %(event_timestamp)s, %(headline)s, %(summary)s, %(raw_text_hash)s, %(dedupe_key)s,
                %(entities_json)s, %(topics_json)s, %(keywords_json)s, %(direction)s, %(direction_confidence)s,
                %(event_confidence)s, %(freshness_seconds)s, %(already_priced_in_state)s,
                %(contradicts_previous_state)s, %(supports_existing_thesis_state)s, %(source_payload_json)s
            )
            ON CONFLICT (dedupe_key) DO UPDATE SET
                source_type=EXCLUDED.source_type,
                raw_source_type=EXCLUDED.raw_source_type,
                source_id=EXCLUDED.source_id,
                source_url=COALESCE(EXCLUDED.source_url, source_event_memory.source_url),
                event_timestamp=COALESCE(EXCLUDED.event_timestamp, source_event_memory.event_timestamp),
                headline=COALESCE(EXCLUDED.headline, source_event_memory.headline),
                summary=COALESCE(EXCLUDED.summary, source_event_memory.summary),
                entities_json=EXCLUDED.entities_json,
                topics_json=EXCLUDED.topics_json,
                keywords_json=EXCLUDED.keywords_json,
                direction=EXCLUDED.direction,
                direction_confidence=EXCLUDED.direction_confidence,
                event_confidence=EXCLUDED.event_confidence,
                freshness_seconds=EXCLUDED.freshness_seconds,
                already_priced_in_state=EXCLUDED.already_priced_in_state,
                contradicts_previous_state=EXCLUDED.contradicts_previous_state,
                supports_existing_thesis_state=EXCLUDED.supports_existing_thesis_state,
                source_payload_json=EXCLUDED.source_payload_json,
                updated_at=now()
            """,
            {
                **event,
                "entities_json": Jsonb(event["entities_json"]),
                "topics_json": Jsonb(event["topics_json"]),
                "keywords_json": Jsonb(event["keywords_json"]),
                "source_payload_json": Jsonb(_jsonable(event["source_payload_json"])),
            },
        )

    def _upsert_link(self, conn: Any, link: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO event_to_market_recall (
                recall_id, source_event_id, market_memory_id, market_id, condition_id, link_type,
                link_confidence, matched_entities_json, matched_topics_json, matched_keywords_json,
                matched_aliases_json, matched_fields_json, confidence_components_json, semantic_score,
                token_side_resolution_state, candidate_actionability_hint, guardrail_reason,
                direction_for_market, direction_confidence, eligible_for_targeted_revalidation, reason
            )
            VALUES (
                %(recall_id)s, %(source_event_id)s, %(market_memory_id)s, %(market_id)s, %(condition_id)s, %(link_type)s,
                %(link_confidence)s, %(matched_entities_json)s, %(matched_topics_json)s, %(matched_keywords_json)s,
                %(matched_aliases_json)s, %(matched_fields_json)s, %(confidence_components_json)s, %(semantic_score)s,
                %(token_side_resolution_state)s, %(candidate_actionability_hint)s, %(guardrail_reason)s,
                %(direction_for_market)s, %(direction_confidence)s, %(eligible_for_targeted_revalidation)s, %(reason)s
            )
            ON CONFLICT (recall_id) DO UPDATE SET
                link_type=EXCLUDED.link_type,
                link_confidence=EXCLUDED.link_confidence,
                matched_entities_json=EXCLUDED.matched_entities_json,
                matched_topics_json=EXCLUDED.matched_topics_json,
                matched_keywords_json=EXCLUDED.matched_keywords_json,
                matched_aliases_json=EXCLUDED.matched_aliases_json,
                matched_fields_json=EXCLUDED.matched_fields_json,
                confidence_components_json=EXCLUDED.confidence_components_json,
                semantic_score=EXCLUDED.semantic_score,
                token_side_resolution_state=EXCLUDED.token_side_resolution_state,
                candidate_actionability_hint=EXCLUDED.candidate_actionability_hint,
                guardrail_reason=EXCLUDED.guardrail_reason,
                direction_for_market=EXCLUDED.direction_for_market,
                direction_confidence=EXCLUDED.direction_confidence,
                eligible_for_targeted_revalidation=EXCLUDED.eligible_for_targeted_revalidation,
                reason=EXCLUDED.reason,
                updated_at=now()
            """,
            {
                **link,
                "matched_entities_json": Jsonb(link["matched_entities_json"]),
                "matched_topics_json": Jsonb(link["matched_topics_json"]),
                "matched_keywords_json": Jsonb(link["matched_keywords_json"]),
                "matched_aliases_json": Jsonb(link.get("matched_aliases_json") or []),
                "matched_fields_json": Jsonb(link["matched_fields_json"]),
                "confidence_components_json": Jsonb(link.get("confidence_components_json") or {}),
            },
        )

    def _update_event_link_summary(self, conn: Any, source_event_id: str) -> None:
        rows = conn.execute(
            """
            SELECT market_id, link_type, link_confidence
            FROM event_to_market_recall
            WHERE source_event_id=%s
            ORDER BY link_confidence DESC, updated_at DESC
            """,
            (source_event_id,),
        ).fetchall()
        linked = [
            {"market_id": row["market_id"], "link_type": row["link_type"], "link_confidence": float(row["link_confidence"] or 0)}
            for row in rows
            if row["link_type"] != "NO_LINK"
        ]
        top = max((item["link_confidence"] for item in linked), default=0.0)
        conn.execute(
            """
            UPDATE source_event_memory
            SET linked_markets_json=%s,
                top_link_confidence=%s,
                updated_at=now()
            WHERE source_event_id=%s
            """,
            (Jsonb(linked[:MAX_LINKS_PER_EVENT]), top, source_event_id),
        )

    def _existing_event(self, conn: Any, dedupe_key: str) -> dict[str, Any] | None:
        return conn.execute("SELECT source_event_id FROM source_event_memory WHERE dedupe_key=%s LIMIT 1", (dedupe_key,)).fetchone()

    def _existing_link(self, conn: Any, recall_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT recall_id FROM event_to_market_recall WHERE recall_id=%s LIMIT 1", (recall_id,)).fetchone()

    def _counts(self, conn: Any) -> dict[str, Any]:
        event_counts = conn.execute(
            """
            SELECT
                COUNT(*) AS total_source_events,
                COUNT(*) FILTER (WHERE updated_at >= now() - interval '72 hours') AS recent_events_count,
                COUNT(*) FILTER (WHERE top_link_confidence > 0) AS linked_events_count,
                COUNT(*) FILTER (WHERE top_link_confidence = 0) AS unlinked_events_count,
                COUNT(*) FILTER (WHERE direction='YES') AS direction_yes,
                COUNT(*) FILTER (WHERE direction='NO') AS direction_no,
                COUNT(*) FILTER (WHERE direction='NEUTRAL') AS direction_neutral,
                COUNT(*) FILTER (WHERE direction='MIXED') AS direction_mixed,
                COUNT(*) FILTER (WHERE direction='UNKNOWN') AS direction_unknown,
                COUNT(*) FILTER (WHERE already_priced_in_state='YES') AS already_priced_in_yes,
                COUNT(*) FILTER (WHERE already_priced_in_state='NO') AS already_priced_in_no,
                COUNT(*) FILTER (WHERE already_priced_in_state='UNKNOWN') AS already_priced_in_unknown,
                COUNT(*) FILTER (WHERE already_priced_in_state='NOT_EVALUATED') AS already_priced_in_not_evaluated,
                COUNT(*) FILTER (WHERE contradicts_previous_state='YES') AS contradicts_previous_yes,
                COUNT(*) FILTER (WHERE contradicts_previous_state='NO') AS contradicts_previous_no,
                COUNT(*) FILTER (WHERE contradicts_previous_state='UNKNOWN') AS contradicts_previous_unknown,
                COUNT(*) FILTER (WHERE contradicts_previous_state='NOT_EVALUATED') AS contradicts_previous_not_evaluated,
                COUNT(*) FILTER (WHERE supports_existing_thesis_state='YES') AS supports_existing_yes,
                COUNT(*) FILTER (WHERE supports_existing_thesis_state='NO') AS supports_existing_no,
                COUNT(*) FILTER (WHERE supports_existing_thesis_state='UNKNOWN') AS supports_existing_unknown,
                COUNT(*) FILTER (WHERE supports_existing_thesis_state='NOT_EVALUATED') AS supports_existing_not_evaluated
            FROM source_event_memory
            """
        ).fetchone()
        type_rows = conn.execute("SELECT source_type, COUNT(*) AS count FROM source_event_memory GROUP BY source_type ORDER BY source_type").fetchall()
        link_rows = conn.execute("SELECT link_type, COUNT(*) AS count FROM event_to_market_recall GROUP BY link_type ORDER BY link_type").fetchall()
        avg_by_type = conn.execute("SELECT link_type, AVG(link_confidence) AS avg_conf FROM event_to_market_recall GROUP BY link_type ORDER BY link_type").fetchall()
        hint_rows = conn.execute("SELECT candidate_actionability_hint, COUNT(*) AS count FROM event_to_market_recall GROUP BY candidate_actionability_hint ORDER BY candidate_actionability_hint").fetchall()
        token_rows = conn.execute("SELECT token_side_resolution_state, COUNT(*) AS count FROM event_to_market_recall GROUP BY token_side_resolution_state ORDER BY token_side_resolution_state").fetchall()
        top_aliases = conn.execute(
            """
            SELECT alias, COUNT(*) AS count
            FROM event_to_market_recall,
                 LATERAL jsonb_array_elements_text(matched_aliases_json) AS alias
            GROUP BY alias
            ORDER BY count DESC, alias
            LIMIT 10
            """
        ).fetchall()
        top_entities = conn.execute(
            """
            SELECT entity, COUNT(*) AS count
            FROM event_to_market_recall,
                 LATERAL jsonb_array_elements_text(matched_entities_json) AS entity
            GROUP BY entity
            ORDER BY count DESC, entity
            LIMIT 10
            """
        ).fetchall()
        top_topics = conn.execute(
            """
            SELECT topic, COUNT(*) AS count
            FROM event_to_market_recall,
                 LATERAL jsonb_array_elements_text(matched_topics_json) AS topic
            GROUP BY topic
            ORDER BY count DESC, topic
            LIMIT 10
            """
        ).fetchall()
        avg = conn.execute("SELECT AVG(link_confidence) AS avg_conf FROM event_to_market_recall WHERE link_type <> 'NO_LINK'").fetchone()
        counts = {key: int(event_counts[key] or 0) for key in event_counts.keys()}
        counts["events_by_source_type"] = {str(row["source_type"]): int(row["count"] or 0) for row in type_rows}
        counts["link_type_counts"] = {key: 0 for key in LINK_TYPES}
        counts["link_type_counts"].update({str(row["link_type"]): int(row["count"] or 0) for row in link_rows})
        counts["average_confidence_by_link_type"] = {str(row["link_type"]): round(float(row["avg_conf"] or 0), 4) for row in avg_by_type}
        counts["candidate_actionability_hint_counts"] = {str(row["candidate_actionability_hint"]): int(row["count"] or 0) for row in hint_rows}
        counts["token_side_resolution_counts"] = {str(row["token_side_resolution_state"]): int(row["count"] or 0) for row in token_rows}
        counts["revalidation_eligible_link_count"] = int(counts["candidate_actionability_hint_counts"].get("REVALIDATION_ELIGIBLE", 0))
        counts["watch_only_link_count"] = int(counts["candidate_actionability_hint_counts"].get("WATCH_ONLY", 0))
        counts["token_side_unknown_count"] = int(counts["token_side_resolution_counts"].get("TOKEN_SIDE_UNKNOWN", 0))
        counts["top_aliases_matched"] = [{"alias": row["alias"], "count": int(row["count"] or 0)} for row in top_aliases]
        counts["top_entities_matched"] = [{"entity": row["entity"], "count": int(row["count"] or 0)} for row in top_entities]
        counts["top_topics_matched"] = [{"topic": row["topic"], "count": int(row["count"] or 0)} for row in top_topics]
        counts["average_link_confidence"] = round(float(avg["avg_conf"] or 0), 4)
        if _table_exists(conn, "targeted_market_revalidations"):
            revalidation = conn.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE revalidation_state IN ('REVALIDATED','PARTIAL')) AS revalidated_market_count,
                    COUNT(*) FILTER (WHERE eligible_for_candidate_generation_later IS TRUE) AS candidate_generation_later_count,
                    (ARRAY_AGG(revalidation_state ORDER BY updated_at DESC, id DESC))[1] AS latest_revalidation_state
                FROM targeted_market_revalidations
                """
            ).fetchone()
            counts["latest_revalidation_state"] = (revalidation or {}).get("latest_revalidation_state")
            counts["revalidated_market_count"] = int((revalidation or {}).get("revalidated_market_count") or 0)
            counts["candidate_generation_later_count"] = int((revalidation or {}).get("candidate_generation_later_count") or 0)
        else:
            counts["latest_revalidation_state"] = None
            counts["revalidated_market_count"] = 0
            counts["candidate_generation_later_count"] = 0
        if _table_exists(conn, "proactive_candidate_seeds"):
            proactive = conn.execute(
                """
                SELECT
                    COUNT(*) AS generated_candidate_seed_count,
                    COUNT(*) FILTER (WHERE side='YES') AS generated_yes_count,
                    COUNT(*) FILTER (WHERE side='NO') AS generated_no_count,
                    COUNT(*) FILTER (WHERE seed_state='WATCH_ONLY' OR side='SIDE_UNKNOWN') AS generated_watch_only_count
                FROM proactive_candidate_seeds
                """
            ).fetchone()
            counts["generated_candidate_seed_count"] = int((proactive or {}).get("generated_candidate_seed_count") or 0)
            counts["generated_yes_count"] = int((proactive or {}).get("generated_yes_count") or 0)
            counts["generated_no_count"] = int((proactive or {}).get("generated_no_count") or 0)
            counts["generated_watch_only_count"] = int((proactive or {}).get("generated_watch_only_count") or 0)
        else:
            counts["generated_candidate_seed_count"] = 0
            counts["generated_yes_count"] = 0
            counts["generated_no_count"] = 0
            counts["generated_watch_only_count"] = 0
        if _table_exists(conn, "research_priority_watchlist"):
            priority = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT emr.market_id) FILTER (WHERE rpw.priority_band='HIGH') AS linked_high_priority_market_count,
                    COUNT(DISTINCT emr.market_id) FILTER (WHERE rpw.scheduler_state='DUE') AS linked_due_market_count
                FROM event_to_market_recall emr
                JOIN research_priority_watchlist rpw ON rpw.market_id=emr.market_id
                WHERE emr.link_type <> 'NO_LINK'
                """
            ).fetchone()
            counts["linked_high_priority_market_count"] = int((priority or {}).get("linked_high_priority_market_count") or 0)
            counts["linked_due_market_count"] = int((priority or {}).get("linked_due_market_count") or 0)
        else:
            counts["linked_high_priority_market_count"] = 0
            counts["linked_due_market_count"] = 0
        return counts

    def _sample_events(self, conn: Any, predicate: str, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"""
            SELECT source_event_id, source_type, source_id, event_timestamp, headline, direction,
                   direction_confidence, event_confidence, top_link_confidence, linked_markets_json
            FROM source_event_memory
            WHERE {predicate}
            ORDER BY top_link_confidence DESC, event_timestamp DESC NULLS LAST, updated_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _sample_links(self, conn: Any, predicate: str, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"""
            SELECT recall_id, source_event_id, market_memory_id, market_id, condition_id,
                   link_type, link_confidence, matched_entities_json, matched_topics_json,
                   matched_keywords_json, matched_aliases_json, matched_fields_json,
                   confidence_components_json, semantic_score, token_side_resolution_state,
                   candidate_actionability_hint, guardrail_reason, direction_for_market,
                   eligible_for_targeted_revalidation,
                   eligible_for_targeted_revalidation AS eligible_for_targeted_revalidation_later,
                   reason
            FROM event_to_market_recall
            WHERE {predicate}
            ORDER BY link_confidence DESC, updated_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _recent_success_exists(self, conn: Any, *, min_interval_seconds: int) -> bool:
        row = conn.execute(
            """
            SELECT completed_at
            FROM source_event_memory_refresh_runs
            WHERE status IN ('OK','PARTIAL')
              AND completed_at >= now() - (%s || ' seconds')::interval
            ORDER BY completed_at DESC, id DESC
            LIMIT 1
            """,
            (min_interval_seconds,),
        ).fetchone()
        return bool(row)

    def _latest_refresh_run(self, conn: Any) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM source_event_memory_refresh_runs
            ORDER BY completed_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def _insert_refresh_run(self, conn: Any, **values: Any) -> None:
        conn.execute(
            """
            INSERT INTO source_event_memory_refresh_runs (
                refresh_run_id, refresh_type, status, started_at, completed_at, source,
                events_seen, events_new, events_updated, duplicate_events, links_created,
                links_updated, unlinked_events, errors_count, latest_error, metadata_json
            )
            VALUES (
                %(refresh_run_id)s, %(refresh_type)s, %(status)s, %(started_at)s, %(completed_at)s, %(source)s,
                %(events_seen)s, %(events_new)s, %(events_updated)s, %(duplicate_events)s, %(links_created)s,
                %(links_updated)s, %(unlinked_events)s, %(errors_count)s, %(latest_error)s, %(metadata_json)s
            )
            ON CONFLICT (refresh_run_id) DO NOTHING
            """,
            {
                "refresh_run_id": values.get("refresh_run_id"),
                "refresh_type": values.get("refresh_type", "SOURCE_EVENT_MEMORY_REFRESH"),
                "status": values.get("status", "UNKNOWN"),
                "started_at": values.get("started_at"),
                "completed_at": values.get("completed_at"),
                "source": values.get("source", "existing_source_tables"),
                "events_seen": values.get("events_seen", 0),
                "events_new": values.get("events_new", 0),
                "events_updated": values.get("events_updated", 0),
                "duplicate_events": values.get("duplicate_events", 0),
                "links_created": values.get("links_created", 0),
                "links_updated": values.get("links_updated", 0),
                "unlinked_events": values.get("unlinked_events", 0),
                "errors_count": values.get("errors_count", 0),
                "latest_error": values.get("latest_error"),
                "metadata_json": Jsonb(_jsonable(values.get("metadata") or {})),
            },
        )

    def _ensure_tables(self, conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_event_memory (
                id BIGSERIAL PRIMARY KEY,
                source_event_id TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL,
                raw_source_type TEXT NULL,
                source_id TEXT NULL,
                source_table TEXT NOT NULL,
                source_record_id TEXT NOT NULL,
                source_url TEXT NULL,
                event_timestamp TIMESTAMPTZ NULL,
                headline TEXT NULL,
                summary TEXT NULL,
                raw_text_hash TEXT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                topics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                direction TEXT NOT NULL DEFAULT 'UNKNOWN',
                direction_confidence NUMERIC NOT NULL DEFAULT 0,
                event_confidence NUMERIC NOT NULL DEFAULT 0,
                freshness_seconds INTEGER NULL,
                already_priced_in_state TEXT NOT NULL DEFAULT 'NOT_EVALUATED',
                contradicts_previous_state TEXT NOT NULL DEFAULT 'NOT_EVALUATED',
                supports_existing_thesis_state TEXT NOT NULL DEFAULT 'NOT_EVALUATED',
                top_link_confidence NUMERIC NOT NULL DEFAULT 0,
                linked_markets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_source_event_memory_dedupe ON source_event_memory (dedupe_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source_event_memory_type_time ON source_event_memory (source_type, event_timestamp DESC NULLS LAST, updated_at DESC)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_to_market_recall (
                id BIGSERIAL PRIMARY KEY,
                recall_id TEXT NOT NULL UNIQUE,
                source_event_id TEXT NOT NULL,
                market_memory_id TEXT NULL,
                market_id TEXT NULL,
                condition_id TEXT NULL,
                link_type TEXT NOT NULL,
                link_confidence NUMERIC NOT NULL DEFAULT 0,
                matched_entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                matched_topics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                matched_keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                matched_aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                matched_fields_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                confidence_components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                semantic_score NUMERIC NOT NULL DEFAULT 0,
                token_side_resolution_state TEXT NOT NULL DEFAULT 'TOKEN_SIDE_UNKNOWN',
                candidate_actionability_hint TEXT NOT NULL DEFAULT 'WATCH_ONLY',
                guardrail_reason TEXT NULL,
                direction_for_market TEXT NOT NULL DEFAULT 'UNKNOWN',
                direction_confidence NUMERIC NOT NULL DEFAULT 0,
                eligible_for_targeted_revalidation BOOLEAN NOT NULL DEFAULT false,
                reason TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        for ddl in (
            "ALTER TABLE event_to_market_recall ADD COLUMN IF NOT EXISTS matched_aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb",
            "ALTER TABLE event_to_market_recall ADD COLUMN IF NOT EXISTS confidence_components_json JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE event_to_market_recall ADD COLUMN IF NOT EXISTS semantic_score NUMERIC NOT NULL DEFAULT 0",
            "ALTER TABLE event_to_market_recall ADD COLUMN IF NOT EXISTS token_side_resolution_state TEXT NOT NULL DEFAULT 'TOKEN_SIDE_UNKNOWN'",
            "ALTER TABLE event_to_market_recall ADD COLUMN IF NOT EXISTS candidate_actionability_hint TEXT NOT NULL DEFAULT 'WATCH_ONLY'",
            "ALTER TABLE event_to_market_recall ADD COLUMN IF NOT EXISTS guardrail_reason TEXT NULL",
        ):
            conn.execute(ddl)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_event_to_market_recall_id ON event_to_market_recall (recall_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_to_market_recall_market ON event_to_market_recall (market_id, link_confidence DESC) WHERE market_id IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_to_market_recall_actionability_hint ON event_to_market_recall (candidate_actionability_hint, link_confidence DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_to_market_recall_token_side_state ON event_to_market_recall (token_side_resolution_state, link_confidence DESC)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_event_memory_refresh_runs (
                id BIGSERIAL PRIMARY KEY,
                refresh_run_id TEXT NOT NULL UNIQUE,
                refresh_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                completed_at TIMESTAMPTZ NULL,
                source TEXT NOT NULL DEFAULT 'existing_source_tables',
                events_seen INTEGER NOT NULL DEFAULT 0,
                events_new INTEGER NOT NULL DEFAULT 0,
                events_updated INTEGER NOT NULL DEFAULT 0,
                duplicate_events INTEGER NOT NULL DEFAULT 0,
                links_created INTEGER NOT NULL DEFAULT 0,
                links_updated INTEGER NOT NULL DEFAULT 0,
                unlinked_events INTEGER NOT NULL DEFAULT 0,
                errors_count INTEGER NOT NULL DEFAULT 0,
                latest_error TEXT NULL,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def _event_seed(row: dict[str, Any], *, source_table: str, source_type: str) -> dict[str, Any]:
    row["source_table"] = source_table
    row["source_type"] = source_type if source_type in SOURCE_TYPES else "UNKNOWN"
    return row


def _normalize_event(row: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    headline = _str_or_none(row.get("headline")) or f"{row.get('source_type')} event {row.get('source_record_id')}"
    summary = _str_or_none(row.get("summary"))
    event_time = _aware(row.get("event_timestamp")) if isinstance(row.get("event_timestamp"), datetime) else now
    raw_text_hash = _str_or_none(row.get("raw_text_hash")) or _hash({"headline": headline, "summary": summary, "source": row.get("source_id")})
    source_table = str(row.get("source_table") or "unknown")
    source_record_id = str(row.get("source_record_id") or raw_text_hash)
    dedupe_key = _dedupe_key(row.get("source_type"), row.get("source_id"), row.get("source_url"), headline, raw_text_hash, event_time)
    source_event_id = f"source_event_{hashlib.sha256(dedupe_key.encode('utf-8')).hexdigest()[:24]}"
    entities, topics = _entities_topics(row)
    keywords = _keywords(" ".join([headline, summary or "", " ".join(entities), " ".join(topics)]))
    direction = _direction(row.get("raw_direction") or row.get("link_direction"))
    direction_conf = _direction_confidence(row, direction)
    return {
        "source_event_id": source_event_id,
        "source_type": row.get("source_type") if row.get("source_type") in SOURCE_TYPES else "UNKNOWN",
        "raw_source_type": _str_or_none(row.get("raw_source_type")),
        "source_id": _str_or_none(row.get("source_id") or row.get("raw_source_id")),
        "source_table": source_table,
        "source_record_id": source_record_id,
        "source_url": _str_or_none(row.get("source_url")),
        "event_timestamp": event_time,
        "headline": headline,
        "summary": summary,
        "raw_text_hash": raw_text_hash,
        "dedupe_key": dedupe_key,
        "entities_json": entities,
        "topics_json": topics,
        "keywords_json": keywords,
        "direction": direction,
        "direction_confidence": direction_conf,
        "event_confidence": _bounded_float(row.get("event_confidence"), default=0.45),
        "freshness_seconds": max(0, int((now - event_time).total_seconds())),
        "already_priced_in_state": _already_priced_in(row),
        "contradicts_previous_state": _contradicts(row),
        "supports_existing_thesis_state": "NOT_EVALUATED",
        "linked_market_id": _str_or_none(row.get("linked_market_id")),
        "link_direction": _str_or_none(row.get("link_direction")),
        "link_confidence": _bounded_float(row.get("link_confidence") or row.get("link_score"), default=0.0),
        "source_payload_json": _jsonable(row),
    }


def _entities_topics(row: dict[str, Any]) -> tuple[list[str], list[str]]:
    entities: list[str] = []
    topics: list[str] = []
    raw_entities = row.get("entities_json")
    if isinstance(raw_entities, dict):
        for value in raw_entities.values():
            if isinstance(value, list):
                entities.extend(str(item) for item in value)
            elif value:
                entities.append(str(value))
    elif isinstance(raw_entities, list):
        entities.extend(str(item) for item in raw_entities)
    raw_topics = row.get("topics_json")
    if isinstance(raw_topics, list):
        topics.extend(str(item) for item in raw_topics)
    elif isinstance(raw_topics, dict):
        topics.extend(str(item) for item in raw_topics.values() if item)
    for key in ("topic_class", "enriched_topic_class"):
        if row.get(key):
            topics.append(str(row[key]))
    text = " ".join(str(row.get(key) or "") for key in ("headline", "summary"))
    # Deterministic high-signal proper-noun/entity extraction only.
    for token in re.findall(r"\b[A-Z][A-Za-z0-9&.-]{2,}\b", text):
        if token.upper() not in {"YES", "NO", "THE", "AND"}:
            entities.append(token)
    return _unique_norm(entities)[:30], _unique_norm(topics)[:30]


def _keywords(text: str) -> list[str]:
    stop = {"the", "and", "for", "with", "will", "this", "that", "from", "market", "event", "unknown"}
    words = [word for word in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", text.lower()) if word not in stop]
    return _unique(words)[:50]


def _title_contains(event: dict[str, Any], market: dict[str, Any]) -> bool:
    text = f"{event.get('headline') or ''} {event.get('summary') or ''}".lower()
    title = str(market.get("title") or market.get("question") or "").lower()
    slug = str(market.get("slug") or "").replace("-", " ").lower()
    title_words = set(_keywords(title))
    if title_words and len(title_words.intersection(set(_keywords(text)))) >= min(3, len(title_words)):
        return True
    slug_words = set(_keywords(slug))
    return bool(slug_words and len(slug_words.intersection(set(_keywords(text)))) >= min(3, len(slug_words)))


def _link_evidence(event: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    market_id = str(market.get("market_id") or "")
    event_text = _event_text(event)
    market_text = _market_text(market)
    event_keywords = set(event.get("keywords_json") or []) - GENERIC_LINK_TERMS
    market_keywords = set(_list(market.get("keywords_json"))) - GENERIC_LINK_TERMS
    event_entities = set(event.get("entities_json") or [])
    market_entities = set(_list(market.get("entities_json")))
    market_text_keywords = set(_keywords(market_text)) - GENERIC_LINK_TERMS
    event_text_keywords = set(_keywords(event_text)) - GENERIC_LINK_TERMS
    event_topics = set(event.get("topics_json") or [])
    market_topics = set(_list(market.get("tags_json")))

    matched_entities = sorted(
        event_entities.intersection(market_entities)
        | {entity for entity in event_entities if _norm(entity) in market_text_keywords}
        | {word for word in event_text_keywords.intersection(market_text_keywords) if word in _entity_like_terms()}
    )
    matched_topics = sorted(event_topics.intersection(market_topics) | _topic_matches(event_text, market_text))
    matched_keywords = sorted(event_keywords.intersection(market_keywords))
    matched_aliases = _alias_matches(event_text, market_text)

    matched_fields: list[str] = []
    identifier_score = 0.0
    linked_market_id = event.get("linked_market_id")
    if linked_market_id and str(linked_market_id) == market_id:
        identifier_score = max(identifier_score, _bounded_float(event.get("link_confidence"), default=0.86))
        matched_fields.append("market_id")
    if event.get("condition_id") and market.get("condition_id") and str(event.get("condition_id")) == str(market.get("condition_id")):
        identifier_score = max(identifier_score, 0.95)
        matched_fields.append("condition_id")
    token_side_state = _token_side_state(event, market)
    if token_side_state in {"TOKEN_SIDE_DIRECT", "TOKEN_SIDE_CONFLICT"}:
        identifier_score = max(identifier_score, 0.92)
        matched_fields.append("token_id")
    if _slug_match(event_text, market):
        identifier_score = max(identifier_score, 0.88)
        matched_fields.append("slug")

    title_match = _title_contains(event, market)
    title_score = 0.0
    if title_match:
        title_score = 0.28
        matched_fields.append("title_or_slug")
    entity_score = min(0.12 * len(matched_entities), 0.32)
    topic_score = min(0.10 * len(matched_topics), 0.30)
    keyword_score = min(0.025 * len(matched_keywords), 0.18)
    alias_score = min(0.15 * len(matched_aliases), 0.42)
    if len(matched_aliases) >= 2 and matched_topics:
        alias_score = min(alias_score + 0.08, 0.42)
    semantic_score = _semantic_score(event_text_keywords, market_text_keywords)
    recency_boost = _recency_boost(event)
    broadness_penalty = _broadness_penalty(matched_entities, matched_topics, matched_keywords, matched_aliases, identifier_score, title_score)
    ambiguity_penalty = 0.05 if len(event_text_keywords) <= 3 and identifier_score == 0 and not matched_aliases else 0.0
    conflict_penalty = 0.10 if _direction(event.get("link_direction") or event.get("direction")) == "MIXED" else 0.0
    confidence = _clamp01(
        identifier_score
        + title_score
        + entity_score
        + topic_score
        + keyword_score
        + alias_score
        + semantic_score
        + recency_boost
        - broadness_penalty
        - ambiguity_penalty
        - conflict_penalty
    )
    if matched_entities:
        matched_fields.append("entities")
    if matched_topics:
        matched_fields.append("topics")
    if matched_keywords:
        matched_fields.append("keywords")
    if matched_aliases:
        matched_fields.append("aliases")
    if semantic_score:
        matched_fields.append("semantic_token_overlap")
    components = {
        "identifier_score": round(identifier_score, 4),
        "title_score": round(title_score, 4),
        "entity_score": round(entity_score, 4),
        "topic_score": round(topic_score, 4),
        "keyword_score": round(keyword_score, 4),
        "alias_score": round(alias_score, 4),
        "semantic_score": round(semantic_score, 4),
        "recency_boost": round(recency_boost, 4),
        "ambiguity_penalty": round(ambiguity_penalty, 4),
        "broadness_penalty": round(broadness_penalty, 4),
        "conflict_penalty": round(conflict_penalty, 4),
    }
    return {
        "confidence": round(confidence, 4),
        "direct": bool(identifier_score >= 0.85 or title_match),
        "matched_entities": matched_entities,
        "matched_topics": matched_topics,
        "matched_keywords": matched_keywords,
        "matched_aliases": matched_aliases,
        "matched_fields": _unique(matched_fields),
        "components": components,
        "semantic_score": round(semantic_score, 4),
        "token_side_resolution_state": token_side_state,
    }


def _link_type(confidence: float, *, direct: bool = False, identifier: bool = False, entity_topic: bool = False) -> str:
    if identifier or (direct and confidence >= 0.85) or (entity_topic and confidence >= 0.78):
        return "DIRECT_LINK"
    if confidence >= 0.65:
        return "LIKELY_LINK"
    if confidence >= 0.35:
        return "WEAK_LINK"
    if confidence >= 0.20:
        return "CONTEXT_ONLY"
    return "NO_LINK"


def _event_text(event: dict[str, Any]) -> str:
    return " ".join(
        str(part or "")
        for part in [
            event.get("headline"),
            event.get("summary"),
            " ".join(event.get("entities_json") or []),
            " ".join(event.get("topics_json") or []),
            " ".join(event.get("keywords_json") or []),
            event.get("source_url"),
            event.get("condition_id"),
            event.get("token_id"),
        ]
    ).lower()


def _market_text(market: dict[str, Any]) -> str:
    return " ".join(
        str(part or "")
        for part in [
            market.get("market_id"),
            market.get("condition_id"),
            market.get("slug"),
            market.get("title"),
            market.get("question"),
            market.get("category"),
            " ".join(_list(market.get("tags_json"))),
            " ".join(_list(market.get("entities_json"))),
            " ".join(_list(market.get("keywords_json"))),
            market.get("yes_token_id"),
            market.get("no_token_id"),
        ]
    ).lower()


def _alias_matches(event_text: str, market_text: str) -> list[str]:
    matches: list[str] = []
    for canonical, aliases in ALIAS_GROUPS.items():
        event_hit = any(_contains_term(event_text, alias) for alias in aliases)
        market_hit = any(_contains_term(market_text, alias) for alias in aliases) or _contains_term(market_text, canonical)
        if event_hit and market_hit:
            matches.append(canonical)
    return _unique(matches)


def _topic_matches(event_text: str, market_text: str) -> set[str]:
    topics: dict[str, tuple[str, ...]] = {
        "etf_approval": ("etf", "approval", "approve", "approved", "deadline", "spot"),
        "crypto_regulation": ("sec", "regulation", "regulatory", "securities", "crypto", "cryptocurrency"),
        "inflation_data": ("cpi", "inflation", "consumer price", "data"),
        "fed_rate_decision": ("fed", "fomc", "rate", "interest", "federal reserve"),
        "election": ("election", "vote", "poll", "nomination", "president"),
        "court_ruling": ("court", "ruling", "lawsuit", "legal", "judge"),
    }
    matched: set[str] = set()
    for name, words in topics.items():
        event_count = sum(1 for word in words if _contains_term(event_text, word))
        market_count = sum(1 for word in words if _contains_term(market_text, word))
        if event_count >= 2 and market_count >= 1:
            matched.add(name)
    return matched


def _semantic_score(event_keywords: set[str], market_keywords: set[str]) -> float:
    event_keywords = {word for word in event_keywords if word not in GENERIC_LINK_TERMS}
    market_keywords = {word for word in market_keywords if word not in GENERIC_LINK_TERMS}
    if not event_keywords or not market_keywords:
        return 0.0
    intersection = event_keywords.intersection(market_keywords)
    if not intersection:
        return 0.0
    jaccard = len(intersection) / max(len(event_keywords.union(market_keywords)), 1)
    return round(min(jaccard * 0.22, 0.18), 4)


def _token_side_state(event: dict[str, Any], market: dict[str, Any]) -> str:
    token = _str_or_none(event.get("token_id"))
    yes_token = _str_or_none(market.get("yes_token_id"))
    no_token = _str_or_none(market.get("no_token_id"))
    direction = _direction(event.get("link_direction") or event.get("direction"))
    if token and token in {yes_token, no_token}:
        if (token == yes_token and direction == "NO") or (token == no_token and direction == "YES"):
            return "TOKEN_SIDE_CONFLICT"
        return "TOKEN_SIDE_DIRECT"
    if token and yes_token and no_token and token not in {yes_token, no_token}:
        return "TOKEN_SIDE_CONFLICT"
    if direction == "YES":
        return "SIDE_DIRECTIONAL_YES"
    if direction == "NO":
        return "SIDE_DIRECTIONAL_NO"
    if direction == "NEUTRAL":
        return "SIDE_DIRECTIONAL_NEUTRAL"
    if direction == "MIXED":
        return "SIDE_DIRECTIONAL_MIXED"
    if event.get("linked_market_id"):
        return "MARKET_LEVEL_ONLY"
    return "TOKEN_SIDE_UNKNOWN"


def _actionability_hint(link_type: str, confidence: float, token_side_state: str, direction: str) -> tuple[str, bool, str]:
    if link_type == "NO_LINK":
        return "NOT_RELEVANT", False, "NO_MARKET_RELATION"
    if confidence < 0.35:
        return "BLOCKED_BY_LOW_CONFIDENCE", False, "LOW_CONFIDENCE_CONTEXT_ONLY"
    if token_side_state == "TOKEN_SIDE_CONFLICT":
        return "BLOCKED_BY_CONFLICT", False, "TOKEN_SIDE_CONFLICT"
    if link_type in {"WEAK_LINK", "CONTEXT_ONLY"}:
        return "CONTEXT_ONLY", False, f"{link_type}_NOT_REVALIDATION_ELIGIBLE"
    if token_side_state in {"TOKEN_SIDE_UNKNOWN", "MARKET_LEVEL_ONLY"} or direction in {"UNKNOWN", "MIXED"}:
        return "WATCH_ONLY", link_type == "DIRECT_LINK" or (link_type == "LIKELY_LINK" and confidence >= 0.70), "TOKEN_SIDE_OR_DIRECTION_NOT_CANDIDATE_ACTIONABLE"
    return "REVALIDATION_ELIGIBLE", link_type == "DIRECT_LINK" or (link_type == "LIKELY_LINK" and confidence >= 0.70), "DIRECT_OR_HIGH_CONFIDENCE_LIKELY_LINK"


def _recency_boost(event: dict[str, Any]) -> float:
    seconds = event.get("freshness_seconds")
    if not isinstance(seconds, int):
        return 0.0
    if seconds <= 6 * 3600:
        return 0.03
    if seconds <= 24 * 3600:
        return 0.015
    return 0.0


def _broadness_penalty(entities: list[str], topics: set[str] | list[str], keywords: list[str], aliases: list[str], identifier_score: float, title_score: float) -> float:
    if identifier_score or title_score:
        return 0.0
    concrete = len(entities) + len(aliases)
    if concrete:
        return 0.0
    if topics and len(keywords) <= 2:
        return 0.08
    if keywords and all(word in GENERIC_LINK_TERMS for word in keywords):
        return 0.12
    return 0.0


def _slug_match(event_text: str, market: dict[str, Any]) -> bool:
    slug = str(market.get("slug") or "").replace("-", " ").lower().strip()
    return bool(slug and len(slug) > 4 and slug in event_text)


def _contains_term(text: str, term: str) -> bool:
    term = term.lower().strip()
    if not term:
        return False
    if " " in term or "-" in term or "." in term:
        return term in text
    return bool(re.search(rf"\b{re.escape(term)}\b", text))


def _entity_like_terms() -> set[str]:
    terms: set[str] = set()
    for canonical, aliases in ALIAS_GROUPS.items():
        terms.add(_norm(canonical))
        terms.update(_norm(alias) for alias in aliases if " " not in alias)
    return {term for term in terms if term}


def _empty_components() -> dict[str, float]:
    return {
        "identifier_score": 0.0,
        "title_score": 0.0,
        "entity_score": 0.0,
        "topic_score": 0.0,
        "keyword_score": 0.0,
        "alias_score": 0.0,
        "semantic_score": 0.0,
        "recency_boost": 0.0,
        "ambiguity_penalty": 0.0,
        "broadness_penalty": 0.0,
        "conflict_penalty": 0.0,
    }


def _linker_thresholds() -> dict[str, Any]:
    return {
        "direct": "identifier exact or confidence >= 0.85 with direct evidence",
        "likely": "confidence >= 0.65",
        "weak": "confidence >= 0.35",
        "context_only": "confidence >= 0.20",
        "no_link": "confidence < 0.20",
        "stage3_revalidation_candidate": "DIRECT_LINK or LIKELY_LINK >= 0.70, still DATA_ONLY",
    }


def _alias_count() -> int:
    return sum(len(values) for values in ALIAS_GROUPS.values())


def _direction(value: Any) -> str:
    raw = str(value or "").upper()
    if raw in {"YES", "NO"}:
        return raw
    if raw in {"UP", "BULLISH", "POSITIVE", "BUY", "LONG", "FOLLOW"}:
        return "YES"
    if raw in {"DOWN", "BEARISH", "NEGATIVE", "SELL", "SHORT"}:
        return "NO"
    if raw in {"BOTH", "MIXED", "CONFLICT"}:
        return "MIXED"
    if raw in {"NONE", "NEUTRAL"}:
        return "NEUTRAL"
    return "UNKNOWN"


def _direction_confidence(row: dict[str, Any], direction: str) -> float:
    if direction == "UNKNOWN":
        return 0.0
    return _bounded_float(row.get("direction_strength") or row.get("event_confidence") or row.get("link_confidence"), default=0.35)


def _already_priced_in(row: dict[str, Any]) -> str:
    value = row.get("already_priced_in_value")
    if value is None:
        return "NOT_EVALUATED"
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if raw >= 0.75:
        return "YES"
    if raw <= 0.25:
        return "NO"
    return "UNKNOWN"


def _contradicts(row: dict[str, Any]) -> str:
    raw = str(row.get("contradiction_hint_class") or "").upper()
    if raw in {"STRONG", "POSSIBLE"}:
        return "YES"
    if raw == "NONE":
        return "NO"
    return "NOT_EVALUATED"


def _news_type(raw_source_type: Any, source_id: Any) -> str:
    raw = f"{raw_source_type or ''} {source_id or ''}".upper()
    if "CRYPTOPANIC" in raw or "CRYPTO_PANIC" in raw:
        return "CRYPTOPANIC"
    if "RSS" in raw:
        return "RSS"
    return "NEWS"


def _recall_id(source_event_id: str, market_key: Any, link_type: str) -> str:
    raw = f"{source_event_id}|{market_key}|{link_type}"
    return f"event_recall_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _dedupe_key(source_type: Any, source_id: Any, source_url: Any, headline: str, raw_hash: str, event_time: datetime) -> str:
    bucket = event_time.strftime("%Y%m%d%H")
    raw = "|".join([str(source_type or "UNKNOWN"), str(source_id or ""), str(source_url or ""), _norm(headline), raw_hash, bucket])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _link_state(link_type: Any, confidence: float) -> str:
    if link_type == "DIRECT_LINK":
        return "DIRECT_EVENT_LINK"
    if link_type == "LIKELY_LINK":
        return "LIKELY_EVENT_LINK"
    if link_type in {"WEAK_LINK", "CONTEXT_ONLY"}:
        return str(link_type)
    return "EVENT_NOT_LINKED"


def _empty_link_fields() -> dict[str, Any]:
    return {
        "recent_source_event_count": 0,
        "strongest_event_link_type": None,
        "strongest_event_link_confidence": 0.0,
        "recent_directional_event_state": "UNKNOWN",
        "recent_source_event_link_state": "EVENT_NOT_LINKED",
        "recall_link_state": "EVENT_NOT_LINKED",
        "event_link_actionability_hint": "NOT_RELEVANT",
        "token_side_resolution_state": "TOKEN_SIDE_UNKNOWN",
        "event_link_guardrail_reason": None,
        "direct_event_link_count": 0,
        "likely_event_link_count": 0,
        "source_event_memory_ids": [],
        "event_to_market_link_ids": [],
        "downstream_seed_mesh_count": 0,
        "downstream_edge_supported_count": 0,
    }


def _empty_summary(status: str, now: datetime) -> dict[str, Any]:
    return {
        "status": status,
        "source": "source_event_memory",
        "last_updated": now.isoformat(),
        "freshness_state": "MISSING",
        "readiness_state": "UNKNOWN",
        "truth_state": "UNKNOWN",
        "counts": {},
        "latest_refresh": None,
        "sample_top_linked_events": [],
        "sample_unlinked_events": [],
        "sample_direct_links": [],
        "sample_likely_links": [],
        "warnings": ["Source event memory is unavailable."],
        "errors": [],
    }


def _bounded_float(value: Any, *, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        raw = float(value)
    except (TypeError, ValueError):
        return default
    return _clamp01(raw if raw <= 1 else raw / 100)


def _clamp01(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_norm(item) for item in value if _norm(item)]
    if isinstance(value, dict):
        return [_norm(item) for item in value.values() if _norm(item)]
    return []


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def _unique_norm(values: list[Any]) -> list[str]:
    return _unique([_norm(value) for value in values if _norm(value)])


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _safety_counts(conn: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "live_orders", "positions", "shadow_orders", "real_orders"):
        out[table] = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0) if _table_exists(conn, table) else 0
    return out


def _trading_mutation(before: dict[str, int], after: dict[str, int]) -> bool:
    return any(after.get(key, 0) > before.get(key, 0) for key in before)
