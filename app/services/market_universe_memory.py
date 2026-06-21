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


FRESH_AFTER = timedelta(hours=24)
STALE_AFTER = timedelta(days=7)
FULL_REFRESH_INTERVAL_SECONDS = 3600


class MarketUniverseMemoryService:
    """DATA_ONLY market universe memory projection.

    The service projects verified local Polymarket connector truth from
    `markets_v2`, latest market snapshots, and latest token orderbooks into one
    queryable universe-memory surface. It never creates candidates, intents,
    orders, fills, positions, or balance mutations.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def refresh_universe(
        self,
        *,
        refresh_type: str = "UNIVERSE_SNAPSHOT",
        force: bool = False,
        min_interval_seconds: int = FULL_REFRESH_INTERVAL_SECONDS,
        limit: int | None = None,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"market_universe_refresh_{uuid4().hex}"
        if not self._factory.enabled:
            return {
                "status": "DATABASE_UNAVAILABLE",
                "refresh_run_id": run_id,
                "markets_seen": 0,
                "markets_new": 0,
                "markets_updated": 0,
                "markets_changed": 0,
                "errors_count": 0,
            }
        with self._factory.connect() as conn, conn.transaction():
            self._ensure_tables(conn)
            if not _table_exists(conn, "markets_v2"):
                self._insert_refresh_run(
                    conn,
                    refresh_run_id=run_id,
                    refresh_type=refresh_type,
                    status="BLOCKED",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    latest_error="markets_v2 missing",
                    metadata={"blocker": "MARKETS_V2_MISSING"},
                )
                return {"status": "BLOCKED", "refresh_run_id": run_id, "latest_error": "markets_v2 missing"}
            if not force and self._recent_success_exists(conn, min_interval_seconds=min_interval_seconds):
                latest = self._latest_refresh_run(conn)
                return {
                    "status": "SKIPPED_RECENT",
                    "refresh_run_id": latest.get("refresh_run_id") if latest else run_id,
                    "latest_refresh": _jsonable(latest),
                    "required_to_pass": [f"Wait at least {min_interval_seconds}s between full universe refreshes or pass force=true."],
                }

            safety_before = _safety_counts(conn)
            rows = self._source_market_rows(conn, limit=limit)
            stats = {
                "markets_seen": 0,
                "markets_new": 0,
                "markets_updated": 0,
                "markets_changed": 0,
                "markets_closed": 0,
                "markets_resolved": 0,
                "markets_stale": 0,
                "markets_unresolved": 0,
                "errors_count": 0,
            }
            errors: list[str] = []
            for row in rows:
                try:
                    record = self._memory_record(dict(row), now=started_at)
                    existing = self._get_existing_by_memory_id(conn, record["market_memory_id"])
                    changed = bool(existing and existing.get("source_payload_hash") != record.get("source_payload_hash"))
                    created = existing is None
                    self._upsert_memory(conn, record)
                    stats["markets_seen"] += 1
                    stats["markets_new"] += int(created)
                    stats["markets_updated"] += int(not created)
                    stats["markets_changed"] += int(changed)
                    stats["markets_closed"] += int(record["status"] in {"CLOSED", "ARCHIVED"})
                    stats["markets_resolved"] += int(record["status"] == "RESOLVED")
                    stats["markets_stale"] += int(record["freshness_state"] != "FRESH")
                    stats["markets_unresolved"] += int(record["identity_verification_state"] == "UNRESOLVED")
                except Exception as exc:
                    stats["errors_count"] += 1
                    errors.append(f"{type(exc).__name__}: {exc}")
            self._mark_absent_memory_stale(conn, started_at)
            safety_after = _safety_counts(conn)
            status = "OK" if not errors else "PARTIAL" if stats["markets_seen"] else "ERROR"
            completed_at = datetime.now(UTC)
            self._insert_refresh_run(
                conn,
                refresh_run_id=run_id,
                refresh_type=refresh_type,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                latest_error=errors[0] if errors else None,
                **stats,
                metadata={
                    "source_table": "markets_v2",
                    "snapshot_sources": ["market_snapshots_v2", "orderbook_snapshots"],
                    "safety_before": safety_before,
                    "safety_after": safety_after,
                    "trading_mutation": _trading_mutation(safety_before, safety_after),
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

    def refresh_market(self, *, market_id: str | None = None, condition_id: str | None = None, token_id: str | None = None, slug: str | None = None) -> dict[str, Any]:
        if not any((market_id, condition_id, token_id, slug)):
            return {"status": "BLOCKED", "blocker": "LOOKUP_KEY_REQUIRED"}
        return self.refresh_universe(refresh_type="TARGETED_MARKET_REFRESH", force=True, limit=None)

    def summary(self, *, limit: int = 10) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return _empty_summary("DATABASE_UNAVAILABLE", now)
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            counts = _memory_counts(conn)
            latest = self._latest_refresh_run(conn)
            high = self._sample(conn, "research_priority='HIGH' AND status='ACTIVE'", limit=limit)
            unresolved = self._sample(conn, "identity_verification_state='UNRESOLVED'", limit=limit)
            mismatch = self._sample(conn, "token_verification_state='TOKENS_MISMATCH'", limit=limit)
        status = "REAL" if counts["total_markets"] else "MISSING"
        return {
            "status": status,
            "source": "market_universe_memory + markets_v2 + market_snapshots_v2 + orderbook_snapshots",
            "last_updated": (latest or {}).get("completed_at") or now.isoformat(),
            "freshness_state": "FRESH" if latest and counts["total_markets"] else "MISSING",
            "readiness_state": "READY" if counts["total_markets"] else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if counts["total_markets"] else "UNKNOWN",
            "counts": counts,
            "latest_refresh": _jsonable(latest),
            "top_high_priority_markets": high,
            "sample_unresolved_markets": unresolved,
            "sample_token_mismatch_markets": mismatch,
            "warnings": [] if counts["total_markets"] else ["Market universe memory has not been refreshed yet."],
            "errors": [],
            "generated_at": now.isoformat(),
        }

    def lookup(
        self,
        *,
        market_id: str | None = None,
        condition_id: str | None = None,
        token_id: str | None = None,
        slug: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "match": None}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = self._lookup_row(conn, market_id=market_id, condition_id=condition_id, token_id=token_id, slug=slug, title=title)
        return {"status": "FOUND" if row else "NOT_FOUND", "match": _jsonable(dict(row)) if row else None}

    def lookup_fields(self, *, market_id: str | None = None, token_id: str | None = None, condition_id: str | None = None, slug: str | None = None) -> dict[str, Any]:
        match = self.lookup(market_id=market_id, condition_id=condition_id, token_id=token_id, slug=slug).get("match")
        if not match:
            return {
                "market_memory_id": None,
                "market_memory_status": "MISSING",
                "market_memory_freshness": "MISSING",
                "market_identity_verification_state": "UNRESOLVED",
                "token_verification_state": "TOKENS_MISSING",
                "research_priority_band": None,
                "research_priority_score": None,
            }
        fields = {
            "market_memory_id": match.get("market_memory_id"),
            "market_memory_status": match.get("status"),
            "market_memory_freshness": match.get("freshness_state"),
            "market_identity_verification_state": match.get("identity_verification_state"),
            "token_verification_state": match.get("token_verification_state"),
            "market_memory_research_priority": match.get("research_priority"),
        }
        try:
            from app.services.research_priority_watchlist import ResearchPriorityWatchlistService

            fields.update(ResearchPriorityWatchlistService(connection_factory=self._factory).fields_for_market(market_id=match.get("market_id")))
        except Exception as exc:
            fields["research_priority_error"] = f"{type(exc).__name__}: {exc}"
        return fields

    def _source_market_rows(self, conn: Any, *, limit: int | None) -> list[dict[str, Any]]:
        limit_sql = "LIMIT %s" if limit else ""
        params: tuple[Any, ...] = (limit,) if limit else ()
        snapshot_join = """
            LEFT JOIN LATERAL (
                SELECT *
                FROM market_snapshots_v2 ms
                WHERE ms.market_id=m.market_id
                ORDER BY ms.snapshot_at DESC NULLS LAST, ms.id DESC
                LIMIT 1
            ) ms ON true
        """ if _table_exists(conn, "market_snapshots_v2") else ""
        snapshot_select = """
                ms.volume_24h AS latest_volume_24h,
                ms.liquidity AS latest_liquidity,
                ms.spread AS latest_spread,
                ms.current_price_yes,
                ms.current_price_no,
                ms.best_bid AS latest_best_bid,
                ms.best_ask AS latest_best_ask,
                ms.snapshot_at AS latest_market_snapshot_at,
        """ if _table_exists(conn, "market_snapshots_v2") else """
                NULL::numeric AS latest_volume_24h,
                NULL::numeric AS latest_liquidity,
                NULL::numeric AS latest_spread,
                NULL::numeric AS current_price_yes,
                NULL::numeric AS current_price_no,
                NULL::numeric AS latest_best_bid,
                NULL::numeric AS latest_best_ask,
                NULL::timestamptz AS latest_market_snapshot_at,
        """
        orderbook_join = """
            LEFT JOIN LATERAL (
                SELECT *
                FROM orderbook_snapshots obs
                WHERE obs.market_id=m.market_id
                  AND obs.token_id=m.yes_token_id
                ORDER BY obs.collected_at DESC NULLS LAST, obs.snapshot_at DESC NULLS LAST, obs.id DESC
                LIMIT 1
            ) yes_ob ON true
            LEFT JOIN LATERAL (
                SELECT *
                FROM orderbook_snapshots obs
                WHERE obs.market_id=m.market_id
                  AND obs.token_id=m.no_token_id
                ORDER BY obs.collected_at DESC NULLS LAST, obs.snapshot_at DESC NULLS LAST, obs.id DESC
                LIMIT 1
            ) no_ob ON true
        """ if _table_exists(conn, "orderbook_snapshots") else ""
        orderbook_select = """
                yes_ob.best_bid AS best_bid_yes,
                yes_ob.best_ask AS best_ask_yes,
                yes_ob.spread AS spread_yes,
                yes_ob.liquidity_score AS liquidity_score_yes,
                yes_ob.collected_at AS yes_orderbook_collected_at,
                no_ob.best_bid AS best_bid_no,
                no_ob.best_ask AS best_ask_no,
                no_ob.spread AS spread_no,
                no_ob.liquidity_score AS liquidity_score_no,
                no_ob.collected_at AS no_orderbook_collected_at,
        """ if _table_exists(conn, "orderbook_snapshots") else """
                NULL::numeric AS best_bid_yes,
                NULL::numeric AS best_ask_yes,
                NULL::numeric AS spread_yes,
                NULL::numeric AS liquidity_score_yes,
                NULL::timestamptz AS yes_orderbook_collected_at,
                NULL::numeric AS best_bid_no,
                NULL::numeric AS best_ask_no,
                NULL::numeric AS spread_no,
                NULL::numeric AS liquidity_score_no,
                NULL::timestamptz AS no_orderbook_collected_at,
        """
        candidate_join = """
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS candidate_count
                FROM paper_eligibility_candidates pec
                WHERE pec.market_id=m.market_id
            ) pec ON true
        """ if _table_exists(conn, "paper_eligibility_candidates") else ""
        candidate_select = "pec.candidate_count" if _table_exists(conn, "paper_eligibility_candidates") else "0::integer AS candidate_count"
        return conn.execute(
            f"""
            SELECT
                m.*,
                {snapshot_select}
                {orderbook_select}
                {candidate_select}
            FROM markets_v2 m
            {snapshot_join}
            {orderbook_join}
            {candidate_join}
            ORDER BY m.active DESC, m.last_seen_at DESC NULLS LAST, m.updated_at DESC NULLS LAST, m.id DESC
            {limit_sql}
            """,
            params,
        ).fetchall()

    def _memory_record(self, row: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        raw = row.get("raw_market_json") if isinstance(row.get("raw_market_json"), dict) else {}
        metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
        market_id = _str_or_none(row.get("market_id"))
        condition_id = _str_or_none(row.get("condition_id"))
        slug = _str_or_none(row.get("slug"))
        yes_token = _str_or_none(row.get("yes_token_id"))
        no_token = _str_or_none(row.get("no_token_id"))
        title = _str_or_none(row.get("question") or raw.get("title") or raw.get("question"))
        status = _status(row)
        identity_state = _identity_state(market_id, condition_id, slug, title)
        token_state = _token_state(yes_token, no_token, row.get("outcome_tokens_json"))
        last_verified = _max_dt(row.get("last_seen_at"), row.get("updated_at"), row.get("latest_market_snapshot_at"))
        latest_orderbook = _max_dt(row.get("yes_orderbook_collected_at"), row.get("no_orderbook_collected_at"))
        freshness = _freshness_state(last_verified, now)
        outcomes = _outcomes(row.get("outcome_tokens_json"))
        spread = _first_number(row.get("latest_spread"), row.get("spread_yes"), row.get("spread_no"))
        liquidity = _first_number(row.get("latest_liquidity"), row.get("liquidity_score_yes"), row.get("liquidity_score_no"))
        volume = _first_number(row.get("latest_volume_24h"), raw.get("volume24hr"), raw.get("volumeNum"), raw.get("volume"))
        tags = _tags(raw, row)
        keywords = _keywords(title, row.get("category"), tags)
        source_payload = {
            "market": _jsonable({k: row.get(k) for k in ("market_id", "condition_id", "slug", "question", "category", "active", "closed", "archived", "accepting_orders", "close_time", "resolution_time")}),
            "tokens": {"yes": yes_token, "no": no_token, "outcomes": _jsonable(row.get("outcome_tokens_json"))},
            "latest_snapshot": _jsonable({k: row.get(k) for k in ("latest_volume_24h", "latest_liquidity", "latest_spread", "current_price_yes", "current_price_no", "latest_market_snapshot_at")}),
            "latest_orderbook": _jsonable({k: row.get(k) for k in ("best_bid_yes", "best_ask_yes", "best_bid_no", "best_ask_no", "yes_orderbook_collected_at", "no_orderbook_collected_at")}),
        }
        return {
            "market_memory_id": _memory_id(market_id, condition_id, slug, title),
            "market_id": market_id,
            "condition_id": condition_id,
            "clob_market_id": _str_or_none(raw.get("clobMarketId") or raw.get("clob_market_id") or metadata.get("clob_market_id")),
            "slug": slug,
            "question": title,
            "title": title,
            "description": _str_or_none(raw.get("description")),
            "status": status,
            "active": bool(row.get("active")),
            "closed": bool(row.get("closed") or row.get("archived")),
            "resolved": bool(row.get("resolution_time")) and bool(row.get("closed") or row.get("archived")),
            "category": _str_or_none(row.get("category")),
            "tags_json": tags,
            "entities_json": [],
            "keywords_json": keywords,
            "outcomes_json": outcomes,
            "yes_token_id": yes_token,
            "no_token_id": no_token,
            "outcome_token_ids_json": _jsonable(row.get("outcome_tokens_json") or {}),
            "volume": volume,
            "liquidity": liquidity,
            "spread": spread,
            "best_bid_yes": _first_number(row.get("best_bid_yes"), row.get("latest_best_bid")),
            "best_ask_yes": _first_number(row.get("best_ask_yes"), row.get("latest_best_ask")),
            "best_bid_no": _first_number(row.get("best_bid_no")),
            "best_ask_no": _first_number(row.get("best_ask_no")),
            "close_time": row.get("close_time"),
            "resolution_time": row.get("resolution_time"),
            "last_seen_at": row.get("last_seen_at"),
            "last_verified_at": last_verified,
            "last_metadata_refresh_at": row.get("updated_at") or row.get("last_seen_at"),
            "last_orderbook_refresh_at": latest_orderbook,
            "identity_verification_state": identity_state,
            "token_verification_state": token_state,
            "freshness_state": freshness,
            "research_priority": _research_priority(status, row, liquidity, volume, now),
            "source": _str_or_none(row.get("source")) or "existing_connector",
            "source_payload_hash": _hash(source_payload),
            "source_payload_json": source_payload,
        }

    def _upsert_memory(self, conn: Any, record: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO market_universe_memory (
                market_memory_id, market_id, condition_id, clob_market_id, slug, question, title, description,
                status, active, closed, resolved, category, tags_json, entities_json, keywords_json,
                outcomes_json, yes_token_id, no_token_id, outcome_token_ids_json,
                volume, liquidity, spread, best_bid_yes, best_ask_yes, best_bid_no, best_ask_no,
                close_time, resolution_time, last_seen_at, last_verified_at, last_metadata_refresh_at,
                last_orderbook_refresh_at, identity_verification_state, token_verification_state,
                freshness_state, research_priority, source, source_payload_hash, source_payload_json
            )
            VALUES (
                %(market_memory_id)s, %(market_id)s, %(condition_id)s, %(clob_market_id)s, %(slug)s, %(question)s, %(title)s, %(description)s,
                %(status)s, %(active)s, %(closed)s, %(resolved)s, %(category)s, %(tags_json)s, %(entities_json)s, %(keywords_json)s,
                %(outcomes_json)s, %(yes_token_id)s, %(no_token_id)s, %(outcome_token_ids_json)s,
                %(volume)s, %(liquidity)s, %(spread)s, %(best_bid_yes)s, %(best_ask_yes)s, %(best_bid_no)s, %(best_ask_no)s,
                %(close_time)s, %(resolution_time)s, %(last_seen_at)s, %(last_verified_at)s, %(last_metadata_refresh_at)s,
                %(last_orderbook_refresh_at)s, %(identity_verification_state)s, %(token_verification_state)s,
                %(freshness_state)s, %(research_priority)s, %(source)s, %(source_payload_hash)s, %(source_payload_json)s
            )
            ON CONFLICT (market_memory_id) DO UPDATE SET
                market_id=EXCLUDED.market_id,
                condition_id=EXCLUDED.condition_id,
                clob_market_id=EXCLUDED.clob_market_id,
                slug=EXCLUDED.slug,
                question=EXCLUDED.question,
                title=EXCLUDED.title,
                description=EXCLUDED.description,
                status=EXCLUDED.status,
                active=EXCLUDED.active,
                closed=EXCLUDED.closed,
                resolved=EXCLUDED.resolved,
                category=EXCLUDED.category,
                tags_json=EXCLUDED.tags_json,
                entities_json=EXCLUDED.entities_json,
                keywords_json=EXCLUDED.keywords_json,
                outcomes_json=EXCLUDED.outcomes_json,
                yes_token_id=EXCLUDED.yes_token_id,
                no_token_id=EXCLUDED.no_token_id,
                outcome_token_ids_json=EXCLUDED.outcome_token_ids_json,
                volume=EXCLUDED.volume,
                liquidity=EXCLUDED.liquidity,
                spread=EXCLUDED.spread,
                best_bid_yes=EXCLUDED.best_bid_yes,
                best_ask_yes=EXCLUDED.best_ask_yes,
                best_bid_no=EXCLUDED.best_bid_no,
                best_ask_no=EXCLUDED.best_ask_no,
                close_time=EXCLUDED.close_time,
                resolution_time=EXCLUDED.resolution_time,
                last_seen_at=EXCLUDED.last_seen_at,
                last_verified_at=EXCLUDED.last_verified_at,
                last_metadata_refresh_at=EXCLUDED.last_metadata_refresh_at,
                last_orderbook_refresh_at=EXCLUDED.last_orderbook_refresh_at,
                identity_verification_state=EXCLUDED.identity_verification_state,
                token_verification_state=EXCLUDED.token_verification_state,
                freshness_state=EXCLUDED.freshness_state,
                research_priority=EXCLUDED.research_priority,
                source=EXCLUDED.source,
                source_payload_hash=EXCLUDED.source_payload_hash,
                source_payload_json=EXCLUDED.source_payload_json,
                updated_at=now()
            """,
            {**record, **{key: Jsonb(record[key]) for key in ("tags_json", "entities_json", "keywords_json", "outcomes_json", "outcome_token_ids_json", "source_payload_json")}},
        )

    def _lookup_row(self, conn: Any, *, market_id: str | None = None, condition_id: str | None = None, token_id: str | None = None, slug: str | None = None, title: str | None = None) -> dict[str, Any] | None:
        clauses: list[str] = []
        params: list[Any] = []
        if market_id:
            clauses.append("market_id=%s")
            params.append(str(market_id))
        if condition_id:
            clauses.append("condition_id=%s")
            params.append(str(condition_id))
        if token_id:
            clauses.append("(yes_token_id=%s OR no_token_id=%s OR outcome_token_ids_json::text ILIKE %s)")
            params.extend([str(token_id), str(token_id), f"%{str(token_id)}%"])
        if slug:
            clauses.append("slug=%s")
            params.append(str(slug))
        if title:
            clauses.append("LOWER(question)=LOWER(%s)")
            params.append(str(title))
        if not clauses:
            return None
        return conn.execute(
            f"""
            SELECT *
            FROM market_universe_memory
            WHERE {' OR '.join(clauses)}
            ORDER BY
                CASE identity_verification_state WHEN 'VERIFIED' THEN 0 WHEN 'PARTIAL' THEN 1 ELSE 2 END,
                updated_at DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()

    def _sample(self, conn: Any, predicate: str, *, limit: int) -> list[dict[str, Any]]:
        event_select = """
                   COALESCE(recall.recent_linked_events_count, 0) AS recent_linked_events_count,
                   recall.latest_linked_event_at,
                   recall.strongest_recent_link_type,
                   recall.strongest_recent_link_confidence,
                   COALESCE(recall.recent_revalidation_eligible_event_count, 0) AS recent_revalidation_eligible_event_count,
                   COALESCE(recall.recent_watch_only_event_count, 0) AS recent_watch_only_event_count,
                   reval.latest_targeted_revalidation_at,
                   reval.latest_targeted_revalidation_state,
                   COALESCE(reval.recent_revalidated_event_count, 0) AS recent_revalidated_event_count,
                   COALESCE(reval.candidate_generation_later_eligible_count, 0) AS candidate_generation_later_eligible_count,
                   COALESCE(seed.proactive_candidate_seed_count, 0) AS proactive_candidate_seed_count,
                   seed.latest_proactive_seed_at,
                   seed.latest_seed_state,
                   rpw.priority_band AS research_priority_band,
                   rpw.priority_score AS research_priority_score,
                   rpw.next_refresh_due_at,
                   rpw.priority_reasons_json AS watchlist_priority_reasons
        """ if _table_exists(conn, "event_to_market_recall") and _table_exists(conn, "source_event_memory") else """
                   0::integer AS recent_linked_events_count,
                   NULL::timestamptz AS latest_linked_event_at,
                   NULL::text AS strongest_recent_link_type,
                   0::numeric AS strongest_recent_link_confidence,
                   0::integer AS recent_revalidation_eligible_event_count,
                   0::integer AS recent_watch_only_event_count,
                   NULL::timestamptz AS latest_targeted_revalidation_at,
                   NULL::text AS latest_targeted_revalidation_state,
                   0::integer AS recent_revalidated_event_count,
                   0::integer AS candidate_generation_later_eligible_count,
                   0::integer AS proactive_candidate_seed_count,
                   NULL::timestamptz AS latest_proactive_seed_at,
                   NULL::text AS latest_seed_state,
                   NULL::text AS research_priority_band,
                   NULL::numeric AS research_priority_score,
                   NULL::timestamptz AS next_refresh_due_at,
                   '[]'::jsonb AS watchlist_priority_reasons
        """
        event_join = """
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS recent_linked_events_count,
                       COUNT(*) FILTER (WHERE emr.candidate_actionability_hint='REVALIDATION_ELIGIBLE') AS recent_revalidation_eligible_event_count,
                       COUNT(*) FILTER (WHERE emr.candidate_actionability_hint='WATCH_ONLY') AS recent_watch_only_event_count,
                       MAX(sem.event_timestamp) AS latest_linked_event_at,
                       (ARRAY_AGG(emr.link_type ORDER BY emr.link_confidence DESC, emr.updated_at DESC))[1] AS strongest_recent_link_type,
                       MAX(emr.link_confidence) AS strongest_recent_link_confidence
                FROM event_to_market_recall emr
                JOIN source_event_memory sem ON sem.source_event_id=emr.source_event_id
                WHERE emr.market_id=market_universe_memory.market_id
                  AND emr.link_type <> 'NO_LINK'
                  AND emr.created_at >= now() - interval '72 hours'
            ) recall ON true
        """ if _table_exists(conn, "event_to_market_recall") and _table_exists(conn, "source_event_memory") else ""
        revalidation_join = """
            LEFT JOIN LATERAL (
                SELECT MAX(updated_at) AS latest_targeted_revalidation_at,
                       (ARRAY_AGG(revalidation_state ORDER BY updated_at DESC, id DESC))[1] AS latest_targeted_revalidation_state,
                       COUNT(*) FILTER (WHERE updated_at >= now() - interval '72 hours' AND revalidation_state IN ('REVALIDATED','PARTIAL')) AS recent_revalidated_event_count,
                       COUNT(*) FILTER (WHERE updated_at >= now() - interval '72 hours' AND eligible_for_candidate_generation_later IS TRUE) AS candidate_generation_later_eligible_count
                FROM targeted_market_revalidations tmr
                WHERE tmr.market_id=market_universe_memory.market_id
            ) reval ON true
        """ if _table_exists(conn, "targeted_market_revalidations") else """
            LEFT JOIN LATERAL (
                SELECT NULL::timestamptz AS latest_targeted_revalidation_at,
                       NULL::text AS latest_targeted_revalidation_state,
                       0::integer AS recent_revalidated_event_count,
                       0::integer AS candidate_generation_later_eligible_count
            ) reval ON true
        """
        seed_join = """
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS proactive_candidate_seed_count,
                       MAX(updated_at) AS latest_proactive_seed_at,
                       (ARRAY_AGG(seed_state ORDER BY updated_at DESC, id DESC))[1] AS latest_seed_state
                FROM proactive_candidate_seeds pcs
                WHERE pcs.market_id=market_universe_memory.market_id
            ) seed ON true
        """ if _table_exists(conn, "proactive_candidate_seeds") else """
            LEFT JOIN LATERAL (
                SELECT 0::integer AS proactive_candidate_seed_count,
                       NULL::timestamptz AS latest_proactive_seed_at,
                       NULL::text AS latest_seed_state
            ) seed ON true
        """
        watchlist_join = """
            LEFT JOIN LATERAL (
                SELECT priority_band, priority_score, next_refresh_due_at, priority_reasons_json
                FROM research_priority_watchlist rpw
                WHERE rpw.market_id=market_universe_memory.market_id
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
            ) rpw ON true
        """ if _table_exists(conn, "research_priority_watchlist") else """
            LEFT JOIN LATERAL (
                SELECT NULL::text AS priority_band,
                       NULL::numeric AS priority_score,
                       NULL::timestamptz AS next_refresh_due_at,
                       '[]'::jsonb AS priority_reasons_json
            ) rpw ON true
        """
        rows = conn.execute(
            f"""
            SELECT market_memory_id, market_id, condition_id, slug, title, status, active, liquidity,
                   volume, spread, identity_verification_state, token_verification_state,
                   freshness_state, research_priority, last_verified_at,
                   {event_select}
            FROM market_universe_memory
            {event_join}
            {revalidation_join}
            {seed_join}
            {watchlist_join}
            WHERE {predicate}
            ORDER BY research_priority, liquidity DESC NULLS LAST, volume DESC NULLS LAST, updated_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _get_existing_by_memory_id(self, conn: Any, memory_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT market_memory_id, source_payload_hash FROM market_universe_memory WHERE market_memory_id=%s LIMIT 1", (memory_id,)).fetchone()

    def _recent_success_exists(self, conn: Any, *, min_interval_seconds: int) -> bool:
        row = conn.execute(
            """
            SELECT completed_at
            FROM market_universe_refresh_runs
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
            FROM market_universe_refresh_runs
            ORDER BY completed_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def _mark_absent_memory_stale(self, conn: Any, now: datetime) -> None:
        conn.execute(
            """
            UPDATE market_universe_memory
            SET freshness_state='STALE',
                status=CASE WHEN status='ACTIVE' THEN 'STALE' ELSE status END,
                updated_at=now()
            WHERE last_verified_at IS NOT NULL
              AND last_verified_at < %s
              AND status='ACTIVE'
            """,
            (now - STALE_AFTER,),
        )

    def _insert_refresh_run(self, conn: Any, **values: Any) -> None:
        payload = {
            "refresh_run_id": values.get("refresh_run_id"),
            "refresh_type": values.get("refresh_type", "UNIVERSE_SNAPSHOT"),
            "status": values.get("status", "UNKNOWN"),
            "started_at": values.get("started_at"),
            "completed_at": values.get("completed_at"),
            "source": values.get("source", "existing_connector"),
            "markets_seen": values.get("markets_seen", 0),
            "markets_new": values.get("markets_new", 0),
            "markets_updated": values.get("markets_updated", 0),
            "markets_changed": values.get("markets_changed", 0),
            "markets_closed": values.get("markets_closed", 0),
            "markets_resolved": values.get("markets_resolved", 0),
            "markets_stale": values.get("markets_stale", 0),
            "markets_unresolved": values.get("markets_unresolved", 0),
            "errors_count": values.get("errors_count", 0),
            "latest_error": values.get("latest_error"),
            "metadata_json": Jsonb(_jsonable(values.get("metadata") or {})),
        }
        conn.execute(
            """
            INSERT INTO market_universe_refresh_runs (
                refresh_run_id, refresh_type, status, started_at, completed_at, source,
                markets_seen, markets_new, markets_updated, markets_changed, markets_closed,
                markets_resolved, markets_stale, markets_unresolved, errors_count,
                latest_error, metadata_json
            )
            VALUES (
                %(refresh_run_id)s, %(refresh_type)s, %(status)s, %(started_at)s, %(completed_at)s, %(source)s,
                %(markets_seen)s, %(markets_new)s, %(markets_updated)s, %(markets_changed)s, %(markets_closed)s,
                %(markets_resolved)s, %(markets_stale)s, %(markets_unresolved)s, %(errors_count)s,
                %(latest_error)s, %(metadata_json)s
            )
            ON CONFLICT (refresh_run_id) DO NOTHING
            """,
            payload,
        )

    def _ensure_tables(self, conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_universe_memory (
                id BIGSERIAL PRIMARY KEY,
                market_memory_id TEXT NOT NULL UNIQUE,
                market_id TEXT NULL,
                condition_id TEXT NULL,
                clob_market_id TEXT NULL,
                slug TEXT NULL,
                question TEXT NULL,
                title TEXT NULL,
                description TEXT NULL,
                status TEXT NOT NULL DEFAULT 'UNRESOLVED',
                active BOOLEAN NOT NULL DEFAULT false,
                closed BOOLEAN NOT NULL DEFAULT false,
                resolved BOOLEAN NOT NULL DEFAULT false,
                category TEXT NULL,
                tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                outcomes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                yes_token_id TEXT NULL,
                no_token_id TEXT NULL,
                outcome_token_ids_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                volume NUMERIC NULL,
                liquidity NUMERIC NULL,
                spread NUMERIC NULL,
                best_bid_yes NUMERIC NULL,
                best_ask_yes NUMERIC NULL,
                best_bid_no NUMERIC NULL,
                best_ask_no NUMERIC NULL,
                close_time TIMESTAMPTZ NULL,
                resolution_time TIMESTAMPTZ NULL,
                last_seen_at TIMESTAMPTZ NULL,
                last_verified_at TIMESTAMPTZ NULL,
                last_metadata_refresh_at TIMESTAMPTZ NULL,
                last_orderbook_refresh_at TIMESTAMPTZ NULL,
                identity_verification_state TEXT NOT NULL DEFAULT 'UNRESOLVED',
                token_verification_state TEXT NOT NULL DEFAULT 'TOKENS_MISSING',
                freshness_state TEXT NOT NULL DEFAULT 'NEEDS_REFRESH',
                research_priority TEXT NOT NULL DEFAULT 'LOW',
                source TEXT NOT NULL DEFAULT 'existing_connector',
                source_payload_hash TEXT NULL,
                source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_market_universe_memory_market_id ON market_universe_memory (market_id) WHERE market_id IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_market_universe_memory_condition_id ON market_universe_memory (condition_id) WHERE condition_id IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_market_universe_memory_slug ON market_universe_memory (slug) WHERE slug IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_market_universe_memory_yes_token ON market_universe_memory (yes_token_id) WHERE yes_token_id IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_market_universe_memory_no_token ON market_universe_memory (no_token_id) WHERE no_token_id IS NOT NULL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_universe_refresh_runs (
                id BIGSERIAL PRIMARY KEY,
                refresh_run_id TEXT NOT NULL UNIQUE,
                refresh_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                completed_at TIMESTAMPTZ NULL,
                source TEXT NOT NULL DEFAULT 'existing_connector',
                markets_seen INTEGER NOT NULL DEFAULT 0,
                markets_new INTEGER NOT NULL DEFAULT 0,
                markets_updated INTEGER NOT NULL DEFAULT 0,
                markets_changed INTEGER NOT NULL DEFAULT 0,
                markets_closed INTEGER NOT NULL DEFAULT 0,
                markets_resolved INTEGER NOT NULL DEFAULT 0,
                markets_stale INTEGER NOT NULL DEFAULT 0,
                markets_unresolved INTEGER NOT NULL DEFAULT 0,
                errors_count INTEGER NOT NULL DEFAULT 0,
                latest_error TEXT NULL,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def _memory_counts(conn: Any) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_markets,
            COUNT(*) FILTER (WHERE status='ACTIVE') AS active_markets,
            COUNT(*) FILTER (WHERE status='CLOSED') AS closed_markets,
            COUNT(*) FILTER (WHERE status='RESOLVED') AS resolved_markets,
            COUNT(*) FILTER (WHERE status='STALE' OR freshness_state='STALE') AS stale_markets,
            COUNT(*) FILTER (WHERE status='UNRESOLVED' OR identity_verification_state='UNRESOLVED') AS unresolved_markets,
            COUNT(*) FILTER (WHERE token_verification_state='TOKENS_VERIFIED') AS token_verified_count,
            COUNT(*) FILTER (WHERE token_verification_state='TOKENS_MISSING') AS token_missing_count,
            COUNT(*) FILTER (WHERE token_verification_state='TOKENS_MISMATCH') AS token_mismatch_count,
            COUNT(*) FILTER (WHERE status='ARCHIVED') AS archived_markets,
            COUNT(*) FILTER (WHERE research_priority='HIGH') AS research_priority_high,
            COUNT(*) FILTER (WHERE research_priority='MEDIUM') AS research_priority_medium,
            COUNT(*) FILTER (WHERE research_priority='LOW') AS research_priority_low,
            COUNT(*) FILTER (WHERE research_priority='DORMANT') AS research_priority_dormant,
            COUNT(*) FILTER (WHERE research_priority='ARCHIVED') AS research_priority_archived
        FROM market_universe_memory
        """
    ).fetchone()
    return {key: int(row[key] or 0) for key in row.keys()}


def _empty_summary(status: str, now: datetime) -> dict[str, Any]:
    return {
        "status": status,
        "source": "market_universe_memory",
        "last_updated": now.isoformat(),
        "freshness_state": "MISSING",
        "readiness_state": "UNKNOWN",
        "truth_state": "UNKNOWN",
        "counts": {},
        "latest_refresh": None,
        "top_high_priority_markets": [],
        "sample_unresolved_markets": [],
        "sample_token_mismatch_markets": [],
        "warnings": ["Market universe memory is unavailable."],
        "errors": [],
    }


def _status(row: dict[str, Any]) -> str:
    if row.get("resolution_time") and (row.get("closed") or row.get("archived")):
        return "RESOLVED"
    if row.get("archived"):
        return "ARCHIVED"
    if row.get("closed"):
        return "CLOSED"
    if row.get("active") is True:
        return "ACTIVE"
    return "UNRESOLVED"


def _identity_state(market_id: str | None, condition_id: str | None, slug: str | None, title: str | None) -> str:
    if market_id and condition_id and (slug or title):
        return "VERIFIED"
    if market_id or condition_id or slug:
        return "PARTIAL"
    return "UNRESOLVED"


def _token_state(yes: str | None, no: str | None, outcome_tokens: Any) -> str:
    if yes and no and yes == no:
        return "TOKENS_MISMATCH"
    if yes and no:
        return "TOKENS_VERIFIED"
    tokens = outcome_tokens if isinstance(outcome_tokens, dict) else {}
    if tokens and len([value for value in tokens.values() if value]) >= 2:
        return "TOKENS_PARTIAL"
    if yes or no:
        return "TOKENS_PARTIAL"
    return "TOKENS_MISSING"


def _freshness_state(last_verified: datetime | None, now: datetime) -> str:
    if not last_verified:
        return "NEEDS_REFRESH"
    age = now - _aware(last_verified)
    if age <= FRESH_AFTER:
        return "FRESH"
    if age <= STALE_AFTER:
        return "STALE"
    return "NEEDS_REFRESH"


def _research_priority(status: str, row: dict[str, Any], liquidity: float | None, volume: float | None, now: datetime) -> str:
    if status in {"CLOSED", "RESOLVED", "ARCHIVED"}:
        return "ARCHIVED"
    close_time = row.get("close_time")
    closes_soon = isinstance(close_time, datetime) and _aware(close_time) <= now + timedelta(days=7)
    candidate_count = int(row.get("candidate_count") or 0)
    if row.get("active") and (candidate_count > 0 or closes_soon or (liquidity or 0) >= 500 or (volume or 0) >= 1000):
        return "HIGH"
    if row.get("active") and ((liquidity or 0) >= 100 or (volume or 0) >= 100):
        return "MEDIUM"
    if row.get("active") and ((liquidity or 0) > 0 or (volume or 0) > 0):
        return "LOW"
    if row.get("active"):
        return "DORMANT"
    return "LOW"


def _outcomes(tokens: Any) -> list[str]:
    if isinstance(tokens, dict) and tokens:
        keys = [str(key).upper() for key in tokens.keys()]
        if "YES" in keys or "NO" in keys or "yes" in tokens or "no" in tokens:
            return ["YES", "NO"]
        return keys
    return ["YES", "NO"]


def _tags(raw: dict[str, Any], row: dict[str, Any]) -> list[str]:
    tags = raw.get("tags") or raw.get("categories") or []
    if isinstance(tags, str):
        tags = [tags]
    out = [str(item).strip() for item in tags if str(item).strip()] if isinstance(tags, list) else []
    if row.get("category"):
        out.append(str(row["category"]))
    if row.get("market_family"):
        out.append(str(row["market_family"]))
    return _unique(out)


def _keywords(title: str | None, category: Any, tags: list[str]) -> list[str]:
    text = " ".join([title or "", str(category or ""), " ".join(tags)])
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", text.lower())
    return _unique(words)[:40]


def _memory_id(market_id: str | None, condition_id: str | None, slug: str | None, title: str | None) -> str:
    seed = market_id or condition_id or slug or title or f"unresolved:{uuid4().hex}"
    return f"market_memory_{hashlib.sha256(str(seed).encode('utf-8')).hexdigest()[:24]}"


def _hash(payload: Any) -> str:
    raw = json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _first_number(*values: Any) -> float | None:
    for value in values:
        try:
            if value is None or value == "":
                continue
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _max_dt(*values: Any) -> datetime | None:
    dates = [_aware(value) for value in values if isinstance(value, datetime)]
    return max(dates) if dates else None


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


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
