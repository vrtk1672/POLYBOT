from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.proactive_seed_mesh_inquiry import ProactiveSeedMeshInquiryService


DEFAULT_GENERATION_LIMIT = 50
DEFAULT_BLOCKED_SAMPLE_LIMIT = 20
MESH_HANDOFF_SKIPPED_REASON = "SAFE_FULL_MESH_DATA_ONLY_HANDOFF_NOT_FOUND_STAGE4_PREP_ONLY"
LINK_TYPES_ALLOWED = {"DIRECT_LINK", "LIKELY_LINK"}
ACTIVE_MARKET_STATES = {"ACTIVE"}
YES_TOKEN_STATES = {"TOKEN_SIDE_DIRECT", "SIDE_DIRECTIONAL_YES"}
NO_TOKEN_STATES = {"TOKEN_SIDE_DIRECT", "SIDE_DIRECTIONAL_NO"}


class ProactiveCandidateGenerationService:
    """DATA_ONLY proactive research seed generation from Stage 3 revalidation.

    Stage 4 writes only research-only seed truth. It never writes execution
    candidates, paper artifacts, live artifacts, or Mesh approvals.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def refresh(self, *, limit: int = DEFAULT_GENERATION_LIMIT, force: bool = False, blocked_sample_limit: int = DEFAULT_BLOCKED_SAMPLE_LIMIT) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"proactive_candidate_generation_{uuid4().hex}"
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "generation_run_id": run_id, "revalidation_rows_seen": 0}
        limit = max(1, min(int(limit or DEFAULT_GENERATION_LIMIT), 500))
        blocked_sample_limit = max(0, min(int(blocked_sample_limit or 0), 200))
        with self._factory.connect() as conn, conn.transaction():
            self._ensure_tables(conn)
            safety_before = _safety_counts(conn)
            rows = self._eligible_revalidations(conn, limit=limit, force=force)
            blocked_rows = self._blocked_revalidation_samples(conn, limit=blocked_sample_limit, force=force)
            stats = {
                "revalidation_rows_seen": len(rows) + len(blocked_rows),
                "seeds_generated": 0,
                "watch_only_seeds": 0,
                "blocked_seeds": 0,
                "duplicate_seeds": 0,
                "mesh_handoff_sent": 0,
                "mesh_handoff_skipped": 0,
            }
            errors: list[str] = []
            for row in [*rows, *blocked_rows]:
                try:
                    seed = self._build_seed(conn, row, run_id=run_id)
                    existed = self._seed_exists(conn, seed["proactive_candidate_seed_id"])
                    self._upsert_seed(conn, seed)
                    state = str(seed.get("seed_state") or "FAILED")
                    stats["seeds_generated"] += int(state == "GENERATED")
                    stats["watch_only_seeds"] += int(state == "WATCH_ONLY")
                    stats["blocked_seeds"] += int(state in {"BLOCKED", "FAILED"})
                    stats["duplicate_seeds"] += int(existed)
                    stats["mesh_handoff_sent"] += int(seed.get("mesh_handoff_state") == "SENT_DATA_ONLY")
                    stats["mesh_handoff_skipped"] += int(seed.get("mesh_handoff_state") == "SKIPPED")
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    stats["blocked_seeds"] += 1
            safety_after = _safety_counts(conn)
            completed_at = datetime.now(UTC)
            status = "OK" if not errors else "PARTIAL" if any(stats.values()) else "ERROR"
            self._insert_run(
                conn,
                generation_run_id=run_id,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                latest_error=errors[0] if errors else None,
                metadata={
                    "limit": limit,
                    "force": force,
                    "blocked_sample_limit": blocked_sample_limit,
                    "safety_before": safety_before,
                    "safety_after": safety_after,
                    "trading_mutation": _trading_mutation(safety_before, safety_after),
                    "execution_candidates_created": False,
                    "paper_artifacts_created": False,
                    "mesh_handoff_policy": MESH_HANDOFF_SKIPPED_REASON,
                    "errors": errors[:5],
                },
                **stats,
            )
        return {
            "status": status,
            "generation_run_id": run_id,
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
            generated = self._sample(conn, "seed_state='GENERATED'", limit=limit)
            watch = self._sample(conn, "seed_state='WATCH_ONLY'", limit=limit)
            blocked = self._sample(conn, "seed_state IN ('BLOCKED','FAILED')", limit=limit)
        return {
            "status": "REAL" if counts["total_candidate_seeds"] else "MISSING",
            "source": "proactive_candidate_seeds + targeted_market_revalidations",
            "last_updated": (latest or {}).get("completed_at") or now.isoformat(),
            "freshness_state": "FRESH" if latest and counts["total_candidate_seeds"] else "MISSING",
            "readiness_state": "READY" if counts["total_candidate_seeds"] else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if counts["total_candidate_seeds"] else "UNKNOWN",
            "counts": counts,
            "latest_generation_run": _jsonable(latest),
            "top_generated_seeds": generated,
            "top_watch_only_seeds": watch,
            "top_blocked_seeds": blocked,
            "warnings": [] if counts["total_candidate_seeds"] else ["No proactive candidate seeds have been generated yet."],
            "errors": [],
            "generated_at": now.isoformat(),
        }

    def by_market(self, *, market_id: str, limit: int = 20) -> dict[str, Any]:
        return self._by_field("market_id", market_id, limit=limit)

    def by_event(self, *, source_event_id: str, limit: int = 50) -> dict[str, Any]:
        return self._by_field("source_event_id", source_event_id, limit=limit)

    def by_seed(self, *, proactive_candidate_seed_id: str) -> dict[str, Any]:
        if not proactive_candidate_seed_id:
            return {"status": "BLOCKED", "blocker": "PROACTIVE_CANDIDATE_SEED_ID_REQUIRED", "seed": None}
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "seed": None}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                "SELECT * FROM proactive_candidate_seeds WHERE proactive_candidate_seed_id=%s LIMIT 1",
                (proactive_candidate_seed_id,),
            ).fetchone()
        return {"status": "REAL" if row else "MISSING", "seed": _jsonable(dict(row)) if row else None}

    def fields_for_market(self, *, market_id: str | None) -> dict[str, Any]:
        if not market_id or not self._factory.enabled:
            return _empty_market_fields()
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                """
                SELECT *
                FROM proactive_candidate_seeds
                WHERE market_id=%s
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
            counts = conn.execute(
                """
                SELECT
                    COUNT(*) AS proactive_candidate_seed_count,
                    COUNT(*) FILTER (WHERE seed_state='GENERATED') AS generated_seed_count,
                    COUNT(*) FILTER (WHERE seed_state='WATCH_ONLY') AS watch_only_seed_count
                FROM proactive_candidate_seeds
                WHERE market_id=%s
                """,
                (market_id,),
            ).fetchone()
            priority = None
            if _table_exists(conn, "research_priority_watchlist"):
                priority = conn.execute(
                    """
                    SELECT priority_band, priority_score
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
        mesh_fields = ProactiveSeedMeshInquiryService(connection_factory=self._factory).fields_for_seed(
            proactive_candidate_seed_id=str(item.get("proactive_candidate_seed_id") or "")
        )
        return {
            "proactive_candidate_seed_count": int((counts or {}).get("proactive_candidate_seed_count") or 0),
            "generated_seed_count": int((counts or {}).get("generated_seed_count") or 0),
            "watch_only_seed_count": int((counts or {}).get("watch_only_seed_count") or 0),
            "latest_proactive_seed_at": _iso(item.get("updated_at") or item.get("created_at")),
            "latest_seed_state": item.get("seed_state"),
            "latest_proactive_candidate_seed_id": item.get("proactive_candidate_seed_id"),
            "proactive_seed_id": item.get("proactive_candidate_seed_id"),
            "seed_type": item.get("seed_type"),
            "multi_trigger_id": item.get("multi_trigger_id"),
            "trigger_type": item.get("trigger_type"),
            "trigger_score": _float(item.get("trigger_score")),
            "trigger_reasons": item.get("trigger_reasons_json") or [],
            "seed_generation_source": item.get("seed_generation_source") or "EVENT_DRIVEN",
            "research_only": bool(item.get("research_only")),
            "seed_execution_allowed": bool(item.get("execution_allowed")),
            "seed_paper_allowed": bool(item.get("paper_allowed")),
            "seed_shadow_allowed": bool(item.get("shadow_allowed")),
            "seed_live_allowed": bool(item.get("live_allowed")),
            "mesh_handoff_state": item.get("mesh_handoff_state"),
            **mesh_fields,
            "source_market_priority_band": (priority or {}).get("priority_band"),
            "source_market_priority_score": _float((priority or {}).get("priority_score")),
        }

    def revalidation_seed_fields(self, conn: Any, *, targeted_revalidation_id: str | None, market_id: str | None) -> dict[str, Any]:
        if not _table_exists(conn, "proactive_candidate_seeds"):
            return {"generated_seed_count": 0, "watch_only_seed_count": 0, "latest_seed_id": None, "mesh_handoff_state": None}
        params: list[Any] = []
        clauses: list[str] = []
        if targeted_revalidation_id:
            clauses.append("targeted_revalidation_id=%s")
            params.append(targeted_revalidation_id)
        if market_id:
            clauses.append("market_id=%s")
            params.append(market_id)
        if not clauses:
            return {"generated_seed_count": 0, "watch_only_seed_count": 0, "latest_seed_id": None, "mesh_handoff_state": None}
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) FILTER (WHERE seed_state='GENERATED') AS generated_seed_count,
                COUNT(*) FILTER (WHERE seed_state='WATCH_ONLY') AS watch_only_seed_count,
                (ARRAY_AGG(proactive_candidate_seed_id ORDER BY updated_at DESC, id DESC))[1] AS latest_seed_id,
                (ARRAY_AGG(mesh_handoff_state ORDER BY updated_at DESC, id DESC))[1] AS mesh_handoff_state
            FROM proactive_candidate_seeds
            WHERE {' OR '.join(clauses)}
            """,
            tuple(params),
        ).fetchone()
        return {
            "generated_seed_count": int((row or {}).get("generated_seed_count") or 0),
            "watch_only_seed_count": int((row or {}).get("watch_only_seed_count") or 0),
            "latest_seed_id": (row or {}).get("latest_seed_id"),
            "mesh_handoff_state": (row or {}).get("mesh_handoff_state"),
        }

    def _by_field(self, field: str, value: str, *, limit: int) -> dict[str, Any]:
        if not value:
            return {"status": "BLOCKED", "blocker": f"{field.upper()}_REQUIRED", "results": []}
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "results": []}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            rows = conn.execute(
                f"""
                SELECT *
                FROM proactive_candidate_seeds
                WHERE {field}=%s
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (value, limit),
            ).fetchall()
        return {"status": "REAL" if rows else "MISSING", field: value, "results": [_jsonable(dict(row)) for row in rows]}

    def _eligible_revalidations(self, conn: Any, *, limit: int, force: bool) -> list[dict[str, Any]]:
        if not (
            _table_exists(conn, "targeted_market_revalidations")
            and _table_exists(conn, "event_to_market_recall")
            and _table_exists(conn, "market_universe_memory")
        ):
            return []
        skip_existing = "" if force else """
          AND NOT EXISTS (
              SELECT 1
              FROM proactive_candidate_seeds pcs
              WHERE pcs.targeted_revalidation_id=tmr.targeted_revalidation_id
                AND pcs.updated_at >= now() - interval '24 hours'
          )
        """
        rows = conn.execute(
            f"""
            SELECT tmr.*, emr.direction_for_market, emr.direction_confidence,
                   emr.candidate_actionability_hint, emr.guardrail_reason,
                   mum.yes_token_id, mum.no_token_id, mum.status AS market_status, mum.active AS market_active
            FROM targeted_market_revalidations tmr
            LEFT JOIN event_to_market_recall emr ON emr.recall_id=tmr.event_to_market_link_id
            LEFT JOIN market_universe_memory mum ON mum.market_memory_id=tmr.market_memory_id OR mum.market_id=tmr.market_id
            WHERE tmr.eligible_for_candidate_generation_later IS TRUE
              AND tmr.revalidation_state='REVALIDATED'
              AND tmr.market_identity_state='VERIFIED'
              AND tmr.token_verification_state='TOKENS_VERIFIED'
              AND tmr.orderbook_refresh_state='FRESH'
              AND tmr.link_type IN ('DIRECT_LINK','LIKELY_LINK')
              {skip_existing}
            ORDER BY tmr.link_confidence DESC, tmr.updated_at DESC, tmr.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _blocked_revalidation_samples(self, conn: Any, *, limit: int, force: bool) -> list[dict[str, Any]]:
        if limit <= 0 or not (
            _table_exists(conn, "targeted_market_revalidations")
            and _table_exists(conn, "event_to_market_recall")
            and _table_exists(conn, "market_universe_memory")
        ):
            return []
        skip_existing = "" if force else """
          AND NOT EXISTS (
              SELECT 1
              FROM proactive_candidate_seeds pcs
              WHERE pcs.targeted_revalidation_id=tmr.targeted_revalidation_id
                AND pcs.updated_at >= now() - interval '24 hours'
          )
        """
        rows = conn.execute(
            f"""
            SELECT tmr.*, emr.direction_for_market, emr.direction_confidence,
                   emr.candidate_actionability_hint, emr.guardrail_reason,
                   mum.yes_token_id, mum.no_token_id, mum.status AS market_status, mum.active AS market_active
            FROM targeted_market_revalidations tmr
            LEFT JOIN event_to_market_recall emr ON emr.recall_id=tmr.event_to_market_link_id
            LEFT JOIN market_universe_memory mum ON mum.market_memory_id=tmr.market_memory_id OR mum.market_id=tmr.market_id
            WHERE (
                    tmr.revalidation_state <> 'REVALIDATED'
                 OR tmr.eligible_for_candidate_generation_later IS NOT TRUE
                 OR tmr.orderbook_refresh_state <> 'FRESH'
                 OR tmr.token_verification_state <> 'TOKENS_VERIFIED'
                 OR tmr.market_identity_state <> 'VERIFIED'
              )
              {skip_existing}
            ORDER BY tmr.link_confidence DESC, tmr.updated_at DESC, tmr.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _build_seed(self, conn: Any, row: dict[str, Any], *, run_id: str) -> dict[str, Any]:
        blockers = _seed_blockers(row)
        warnings = _soft_warnings(row)
        direction = str(row.get("direction_for_market") or "UNKNOWN").upper()
        direction_conf = _float(row.get("direction_confidence"))
        token_side = str(row.get("token_side_resolution_state") or "TOKEN_SIDE_UNKNOWN")
        side = "SIDE_UNKNOWN"
        token_id = None
        state = "BLOCKED" if blockers else "WATCH_ONLY"
        if not blockers and direction == "YES" and token_side in YES_TOKEN_STATES:
            side = "YES"
            token_id = row.get("yes_token_id")
            state = "GENERATED"
        elif not blockers and direction == "NO" and token_side in NO_TOKEN_STATES:
            side = "NO"
            token_id = row.get("no_token_id")
            state = "GENERATED"
        elif not blockers:
            blockers = []
            warnings.append("SIDE_UNKNOWN_RESEARCH_ONLY")
            state = "WATCH_ONLY"
        if not blockers and state == "GENERATED" and not token_id:
            blockers.append(f"{side}_TOKEN_ID_MISSING")
            state = "BLOCKED"
        if str(row.get("already_priced_in_state") or "UNKNOWN") == "YES":
            warnings.append("EVENT_ALREADY_PRICED_IN")
            if state == "GENERATED":
                state = "WATCH_ONLY"
                side = "SIDE_UNKNOWN"
                token_id = None
        seed_id = _seed_id(row.get("targeted_revalidation_id"), side)
        return {
            "proactive_candidate_seed_id": seed_id,
            "generation_run_id": run_id,
            "source_event_id": row.get("source_event_id"),
            "event_to_market_link_id": row.get("event_to_market_link_id"),
            "targeted_revalidation_id": row.get("targeted_revalidation_id"),
            "market_memory_id": row.get("market_memory_id"),
            "market_id": row.get("market_id"),
            "condition_id": row.get("condition_id"),
            "side": side,
            "token_id": token_id,
            "seed_state": state,
            "seed_type": "EVENT_RECALL_REVALIDATED_MARKET",
            "research_only": True,
            "execution_allowed": False,
            "paper_allowed": False,
            "shadow_allowed": False,
            "live_allowed": False,
            "link_type": row.get("link_type"),
            "link_confidence": _float(row.get("link_confidence")),
            "direction_for_market": direction,
            "direction_confidence": direction_conf,
            "orderbook_snapshot_id": row.get("selected_orderbook_snapshot_id"),
            "orderbook_refresh_state": row.get("orderbook_refresh_state") or "UNKNOWN",
            "liquidity_state": row.get("liquidity_state") or "UNKNOWN",
            "spread_state": row.get("spread_state") or "UNKNOWN",
            "payout_odds_state": row.get("payout_odds_state") or "MISSING",
            "movement_state": row.get("movement_state") or "UNKNOWN",
            "already_priced_in_state": row.get("already_priced_in_state") or "UNKNOWN",
            "candidate_event_scope_state": row.get("candidate_event_scope_state") or "UNKNOWN",
            "token_side_resolution_state": token_side,
            "mesh_handoff_state": "SKIPPED",
            "mesh_inquiry_session_id": None,
            "blockers_json": blockers,
            "soft_warnings_json": warnings,
            "required_to_pass_json": _required_to_pass(blockers, warnings),
            "reason": _reason(state, blockers, warnings),
            "metadata_json": {
                "stage4_execution_triggered": False,
                "paper_intent_created": False,
                "execution_candidate_created": False,
                "mesh_handoff_reason": MESH_HANDOFF_SKIPPED_REASON,
                "candidate_actionability_hint": row.get("candidate_actionability_hint"),
                "guardrail_reason": row.get("guardrail_reason"),
            },
        }

    def _seed_exists(self, conn: Any, seed_id: str) -> bool:
        row = conn.execute("SELECT 1 FROM proactive_candidate_seeds WHERE proactive_candidate_seed_id=%s LIMIT 1", (seed_id,)).fetchone()
        return bool(row)

    def _upsert_seed(self, conn: Any, record: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO proactive_candidate_seeds (
                proactive_candidate_seed_id, generation_run_id, source_event_id, event_to_market_link_id,
                targeted_revalidation_id, market_memory_id, market_id, condition_id, side, token_id,
                seed_state, seed_type, research_only, execution_allowed, paper_allowed, shadow_allowed,
                live_allowed, link_type, link_confidence, direction_for_market, direction_confidence,
                orderbook_snapshot_id, orderbook_refresh_state, liquidity_state, spread_state,
                payout_odds_state, movement_state, already_priced_in_state, candidate_event_scope_state,
                token_side_resolution_state, mesh_handoff_state, mesh_inquiry_session_id,
                blockers_json, soft_warnings_json, required_to_pass_json, reason, metadata_json
            )
            VALUES (
                %(proactive_candidate_seed_id)s, %(generation_run_id)s, %(source_event_id)s, %(event_to_market_link_id)s,
                %(targeted_revalidation_id)s, %(market_memory_id)s, %(market_id)s, %(condition_id)s, %(side)s, %(token_id)s,
                %(seed_state)s, %(seed_type)s, %(research_only)s, %(execution_allowed)s, %(paper_allowed)s, %(shadow_allowed)s,
                %(live_allowed)s, %(link_type)s, %(link_confidence)s, %(direction_for_market)s, %(direction_confidence)s,
                %(orderbook_snapshot_id)s, %(orderbook_refresh_state)s, %(liquidity_state)s, %(spread_state)s,
                %(payout_odds_state)s, %(movement_state)s, %(already_priced_in_state)s, %(candidate_event_scope_state)s,
                %(token_side_resolution_state)s, %(mesh_handoff_state)s, %(mesh_inquiry_session_id)s,
                %(blockers_json)s, %(soft_warnings_json)s, %(required_to_pass_json)s, %(reason)s, %(metadata_json)s
            )
            ON CONFLICT (proactive_candidate_seed_id) DO UPDATE SET
                generation_run_id=EXCLUDED.generation_run_id,
                source_event_id=EXCLUDED.source_event_id,
                event_to_market_link_id=EXCLUDED.event_to_market_link_id,
                targeted_revalidation_id=EXCLUDED.targeted_revalidation_id,
                market_memory_id=EXCLUDED.market_memory_id,
                market_id=EXCLUDED.market_id,
                condition_id=EXCLUDED.condition_id,
                side=EXCLUDED.side,
                token_id=EXCLUDED.token_id,
                seed_state=EXCLUDED.seed_state,
                research_only=EXCLUDED.research_only,
                execution_allowed=EXCLUDED.execution_allowed,
                paper_allowed=EXCLUDED.paper_allowed,
                shadow_allowed=EXCLUDED.shadow_allowed,
                live_allowed=EXCLUDED.live_allowed,
                link_type=EXCLUDED.link_type,
                link_confidence=EXCLUDED.link_confidence,
                direction_for_market=EXCLUDED.direction_for_market,
                direction_confidence=EXCLUDED.direction_confidence,
                orderbook_snapshot_id=EXCLUDED.orderbook_snapshot_id,
                orderbook_refresh_state=EXCLUDED.orderbook_refresh_state,
                liquidity_state=EXCLUDED.liquidity_state,
                spread_state=EXCLUDED.spread_state,
                payout_odds_state=EXCLUDED.payout_odds_state,
                movement_state=EXCLUDED.movement_state,
                already_priced_in_state=EXCLUDED.already_priced_in_state,
                candidate_event_scope_state=EXCLUDED.candidate_event_scope_state,
                token_side_resolution_state=EXCLUDED.token_side_resolution_state,
                mesh_handoff_state=EXCLUDED.mesh_handoff_state,
                blockers_json=EXCLUDED.blockers_json,
                soft_warnings_json=EXCLUDED.soft_warnings_json,
                required_to_pass_json=EXCLUDED.required_to_pass_json,
                reason=EXCLUDED.reason,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            {
                **record,
                "blockers_json": Jsonb(record.get("blockers_json") or []),
                "soft_warnings_json": Jsonb(record.get("soft_warnings_json") or []),
                "required_to_pass_json": Jsonb(record.get("required_to_pass_json") or []),
                "metadata_json": Jsonb(_jsonable(record.get("metadata_json") or {})),
            },
        )

    def _insert_run(self, conn: Any, *, generation_run_id: str, status: str, started_at: datetime, completed_at: datetime, latest_error: str | None, metadata: dict[str, Any], **stats: Any) -> None:
        conn.execute(
            """
            INSERT INTO proactive_candidate_generation_runs (
                generation_run_id, status, started_at, completed_at, revalidation_rows_seen,
                seeds_generated, watch_only_seeds, blocked_seeds, duplicate_seeds,
                mesh_handoff_sent, mesh_handoff_skipped, latest_error, metadata_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (generation_run_id) DO UPDATE SET
                status=EXCLUDED.status,
                completed_at=EXCLUDED.completed_at,
                revalidation_rows_seen=EXCLUDED.revalidation_rows_seen,
                seeds_generated=EXCLUDED.seeds_generated,
                watch_only_seeds=EXCLUDED.watch_only_seeds,
                blocked_seeds=EXCLUDED.blocked_seeds,
                duplicate_seeds=EXCLUDED.duplicate_seeds,
                mesh_handoff_sent=EXCLUDED.mesh_handoff_sent,
                mesh_handoff_skipped=EXCLUDED.mesh_handoff_skipped,
                latest_error=EXCLUDED.latest_error,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            (
                generation_run_id,
                status,
                started_at,
                completed_at,
                int(stats.get("revalidation_rows_seen") or 0),
                int(stats.get("seeds_generated") or 0),
                int(stats.get("watch_only_seeds") or 0),
                int(stats.get("blocked_seeds") or 0),
                int(stats.get("duplicate_seeds") or 0),
                int(stats.get("mesh_handoff_sent") or 0),
                int(stats.get("mesh_handoff_skipped") or 0),
                latest_error,
                Jsonb(_jsonable(metadata)),
            ),
        )

    def _counts(self, conn: Any) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_candidate_seeds,
                COUNT(*) FILTER (WHERE seed_state='GENERATED') AS generated_count,
                COUNT(*) FILTER (WHERE seed_state='WATCH_ONLY') AS watch_only_count,
                COUNT(*) FILTER (WHERE seed_state='BLOCKED') AS blocked_count,
                COUNT(*) FILTER (WHERE side='YES') AS yes_count,
                COUNT(*) FILTER (WHERE side='NO') AS no_count,
                COUNT(*) FILTER (WHERE side='SIDE_UNKNOWN') AS side_unknown_count,
                COUNT(*) FILTER (WHERE mesh_handoff_state='SENT_DATA_ONLY') AS mesh_handoff_sent_count,
                COUNT(*) FILTER (WHERE mesh_handoff_state='SKIPPED') AS mesh_handoff_skipped_count,
                COUNT(DISTINCT source_event_id) AS source_events_used,
                COUNT(DISTINCT market_id) AS markets_used,
                AVG(link_confidence) AS average_link_confidence
            FROM proactive_candidate_seeds
            """
        ).fetchone()
        direction = conn.execute(
            """
            SELECT direction_for_market, COUNT(*) AS count
            FROM proactive_candidate_seeds
            GROUP BY direction_for_market
            ORDER BY direction_for_market
            """
        ).fetchall()
        blocked = conn.execute(
            """
            SELECT blocker, COUNT(*) AS count
            FROM proactive_candidate_seeds,
                 LATERAL jsonb_array_elements_text(blockers_json) AS blocker
            GROUP BY blocker
            ORDER BY count DESC, blocker
            """
        ).fetchall()
        out = {key: int(value or 0) if key.endswith("_count") or key in {"total_candidate_seeds", "source_events_used", "markets_used", "yes_count", "no_count", "side_unknown_count"} else value for key, value in dict(row).items()}
        out["average_link_confidence"] = round(float(out.get("average_link_confidence") or 0.0), 4)
        out["direction_counts"] = {str(item["direction_for_market"]): int(item["count"] or 0) for item in direction}
        out["blocked_skipped_count_by_reason"] = {str(item["blocker"]): int(item["count"] or 0) for item in blocked}
        out["duplicate_skipped_count"] = int((self._latest_run(conn) or {}).get("duplicate_seeds") or 0)
        if _table_exists(conn, "multi_trigger_candidate_triggers"):
            trigger_counts = conn.execute(
                """
                SELECT trigger_type, COUNT(*) AS count
                FROM proactive_candidate_seeds
                WHERE seed_generation_source='MULTI_TRIGGER'
                GROUP BY trigger_type
                ORDER BY count DESC, trigger_type
                """
            ).fetchall()
            out["multi_trigger_seed_count"] = sum(int(item["count"] or 0) for item in trigger_counts)
            out["seeds_by_trigger_type"] = {str(item["trigger_type"]): int(item["count"] or 0) for item in trigger_counts}
        else:
            out["multi_trigger_seed_count"] = 0
            out["seeds_by_trigger_type"] = {}
        return out

    def _latest_run(self, conn: Any) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM proactive_candidate_generation_runs
            ORDER BY completed_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ).fetchone()
        return _jsonable(dict(row)) if row else None

    def _sample(self, conn: Any, where: str, *, limit: int) -> list[dict[str, Any]]:
        if _table_exists(conn, "research_priority_watchlist"):
            priority_select = """
                   rpw.priority_band AS source_market_priority_band,
                   rpw.priority_score AS source_market_priority_score
            """
            priority_join = """
            LEFT JOIN LATERAL (
                SELECT priority_band, priority_score
                FROM research_priority_watchlist rpw
                WHERE rpw.market_id=pcs.market_id
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
            ) rpw ON true
            """
        else:
            priority_select = """
                   NULL::text AS source_market_priority_band,
                   NULL::numeric AS source_market_priority_score
            """
            priority_join = ""
        if _table_exists(conn, "proactive_seed_mesh_inquiries"):
            mesh_select = """
                   smi.mesh_inquiry_request_count,
                   smi.mesh_completed_count,
                   smi.mesh_result_state,
                   smi.edge_state,
                   smi.opportunity_score,
                   smi.opportunity_decision_band
            """
            mesh_join = """
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS mesh_inquiry_request_count,
                       COUNT(*) FILTER (WHERE psi.request_state='COMPLETED') AS mesh_completed_count,
                       (ARRAY_AGG(psr.result_state ORDER BY psi.updated_at DESC, psi.id DESC))[1] AS mesh_result_state,
                       (ARRAY_AGG(psr.edge_state ORDER BY psi.updated_at DESC, psi.id DESC))[1] AS edge_state,
                       (ARRAY_AGG(psr.opportunity_score ORDER BY psi.updated_at DESC, psi.id DESC))[1] AS opportunity_score,
                       (ARRAY_AGG(psr.opportunity_decision_band ORDER BY psi.updated_at DESC, psi.id DESC))[1] AS opportunity_decision_band
                FROM proactive_seed_mesh_inquiries psi
                LEFT JOIN proactive_seed_mesh_results psr ON psr.seed_mesh_inquiry_id=psi.seed_mesh_inquiry_id
                WHERE psi.proactive_candidate_seed_id=pcs.proactive_candidate_seed_id
            ) smi ON true
            """
        else:
            mesh_select = """
                   0::integer AS mesh_inquiry_request_count,
                   0::integer AS mesh_completed_count,
                   NULL::text AS mesh_result_state,
                   NULL::text AS edge_state,
                   NULL::numeric AS opportunity_score,
                   NULL::text AS opportunity_decision_band
            """
            mesh_join = ""
        rows = conn.execute(
            f"""
            SELECT pcs.*,
                   {priority_select},
                   {mesh_select}
            FROM proactive_candidate_seeds pcs
            {priority_join}
            {mesh_join}
            WHERE {where}
            ORDER BY pcs.link_confidence DESC, pcs.updated_at DESC, pcs.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_jsonable(dict(row)) for row in rows]

    def _ensure_tables(self, conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proactive_candidate_seeds (
                id BIGSERIAL PRIMARY KEY,
                proactive_candidate_seed_id TEXT NOT NULL UNIQUE,
                generation_run_id TEXT,
                source_event_id TEXT,
                event_to_market_link_id TEXT,
                targeted_revalidation_id TEXT,
                market_memory_id TEXT,
                market_id TEXT,
                condition_id TEXT,
                side TEXT NOT NULL DEFAULT 'SIDE_UNKNOWN',
                token_id TEXT,
                seed_state TEXT NOT NULL DEFAULT 'GENERATED',
                seed_type TEXT NOT NULL DEFAULT 'EVENT_RECALL_REVALIDATED_MARKET',
                research_only BOOLEAN NOT NULL DEFAULT TRUE,
                execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                paper_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                shadow_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                live_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                link_type TEXT,
                link_confidence NUMERIC NOT NULL DEFAULT 0,
                direction_for_market TEXT NOT NULL DEFAULT 'UNKNOWN',
                direction_confidence NUMERIC NOT NULL DEFAULT 0,
                orderbook_snapshot_id TEXT,
                orderbook_refresh_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                liquidity_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                spread_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                payout_odds_state TEXT NOT NULL DEFAULT 'MISSING',
                movement_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                already_priced_in_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                candidate_event_scope_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                token_side_resolution_state TEXT NOT NULL DEFAULT 'TOKEN_SIDE_UNKNOWN',
                mesh_handoff_state TEXT NOT NULL DEFAULT 'SKIPPED',
                mesh_inquiry_session_id TEXT,
                blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                soft_warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                reason TEXT,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proactive_candidate_generation_runs (
                id BIGSERIAL PRIMARY KEY,
                generation_run_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                revalidation_rows_seen INTEGER NOT NULL DEFAULT 0,
                seeds_generated INTEGER NOT NULL DEFAULT 0,
                watch_only_seeds INTEGER NOT NULL DEFAULT 0,
                blocked_seeds INTEGER NOT NULL DEFAULT 0,
                duplicate_seeds INTEGER NOT NULL DEFAULT 0,
                mesh_handoff_sent INTEGER NOT NULL DEFAULT 0,
                mesh_handoff_skipped INTEGER NOT NULL DEFAULT 0,
                latest_error TEXT,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def _seed_blockers(row: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if row.get("revalidation_state") != "REVALIDATED":
        blockers.append(f"REVALIDATION_NOT_CLEAN_{row.get('revalidation_state') or 'UNKNOWN'}")
    if row.get("eligible_for_candidate_generation_later") is not True:
        blockers.append("REVALIDATION_NOT_CANDIDATE_GENERATION_ELIGIBLE")
    if row.get("market_identity_state") != "VERIFIED":
        blockers.append("MARKET_IDENTITY_NOT_VERIFIED")
    if row.get("token_verification_state") != "TOKENS_VERIFIED":
        blockers.append(str(row.get("token_verification_state") or "TOKENS_NOT_VERIFIED"))
    if row.get("orderbook_refresh_state") != "FRESH":
        blockers.append("ORDERBOOK_NOT_FRESH")
    if str(row.get("link_type") or "") not in LINK_TYPES_ALLOWED:
        blockers.append("LINK_TYPE_NOT_STAGE4_ELIGIBLE")
    if str(row.get("token_side_resolution_state") or "") == "TOKEN_SIDE_CONFLICT":
        blockers.append("TOKEN_SIDE_CONFLICT")
    if str(row.get("market_status") or "ACTIVE") not in ACTIVE_MARKET_STATES or row.get("market_active") is False:
        blockers.append("MARKET_NOT_ACTIVE")
    if str(row.get("candidate_event_scope_state") or "") in {"NOT_ACTIONABLE", "UNKNOWN"}:
        blockers.append("CANDIDATE_EVENT_SCOPE_NOT_RESEARCH_READY")
    raw = row.get("candidate_generation_blockers_json") or []
    if isinstance(raw, list):
        blockers.extend(str(item) for item in raw if item)
    return _dedupe(blockers)


def _soft_warnings(row: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if str(row.get("already_priced_in_state") or "UNKNOWN") in {"UNKNOWN", "NOT_EVALUATED"}:
        warnings.append("ALREADY_PRICED_IN_NOT_CONFIRMED")
    if str(row.get("liquidity_state") or "UNKNOWN") in {"UNKNOWN", "POOR"}:
        warnings.append("LIQUIDITY_NOT_STRONG")
    if str(row.get("spread_state") or "UNKNOWN") in {"UNKNOWN", "WIDE"}:
        warnings.append("SPREAD_NOT_STRONG")
    if str(row.get("movement_state") or "UNKNOWN") == "UNKNOWN":
        warnings.append("MOVEMENT_UNKNOWN")
    if str(row.get("token_side_resolution_state") or "") in {"MARKET_LEVEL_ONLY", "TOKEN_SIDE_UNKNOWN", "SIDE_DIRECTIONAL_NEUTRAL", "SIDE_DIRECTIONAL_MIXED"}:
        warnings.append("TOKEN_SIDE_UNKNOWN_WATCH_ONLY")
    if str(row.get("direction_for_market") or "UNKNOWN") in {"UNKNOWN", "NEUTRAL", "MIXED"}:
        warnings.append("DIRECTION_UNKNOWN_WATCH_ONLY")
    return _dedupe(warnings)


def _required_to_pass(blockers: list[str], warnings: list[str]) -> list[str]:
    out: list[str] = []
    mapping = {
        "ORDERBOOK_NOT_FRESH": "Refresh trusted orderbook for the exact market/token before candidate handoff.",
        "TOKEN_SIDE_CONFLICT": "Resolve token/side conflict without guessing.",
        "TOKEN_SIDE_UNKNOWN_WATCH_ONLY": "Resolve candidate side/token before YES/NO seed handoff.",
        "DIRECTION_UNKNOWN_WATCH_ONLY": "Obtain directional event evidence before YES/NO seed handoff.",
        "MARKET_NOT_ACTIVE": "Market must be active for proactive candidate seeding.",
    }
    for value in [*blockers, *warnings]:
        out.append(mapping.get(value, value))
    return _dedupe(out)


def _reason(state: str, blockers: list[str], warnings: list[str]) -> str:
    if state == "GENERATED":
        return "Clean revalidated market produced research-only proactive candidate seed."
    if state == "WATCH_ONLY":
        return "Research-only watch seed created; side/actionability is not executable."
    return f"Seed blocked: {', '.join(blockers or warnings or ['UNKNOWN'])}."


def _seed_id(targeted_revalidation_id: Any, side: str) -> str:
    key = f"{targeted_revalidation_id or ''}|{side or 'SIDE_UNKNOWN'}"
    return f"proactive_seed_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:32]}"


def _empty_summary(status: str, now: datetime) -> dict[str, Any]:
    return {
        "status": status,
        "source": "proactive_candidate_seeds",
        "last_updated": now.isoformat(),
        "freshness_state": "MISSING",
        "readiness_state": "UNKNOWN",
        "truth_state": "UNKNOWN",
        "counts": {},
        "warnings": ["Database is not configured."],
        "errors": [],
        "generated_at": now.isoformat(),
    }


def _empty_market_fields() -> dict[str, Any]:
    return {
        "proactive_candidate_seed_count": 0,
        "generated_seed_count": 0,
        "watch_only_seed_count": 0,
        "latest_proactive_seed_at": None,
        "latest_seed_state": None,
        "latest_proactive_candidate_seed_id": None,
        "proactive_seed_id": None,
        "seed_type": None,
        "research_only": None,
        "seed_execution_allowed": False,
        "seed_paper_allowed": False,
        "seed_shadow_allowed": False,
        "seed_live_allowed": False,
        "mesh_handoff_state": None,
    }


def _safety_counts(conn: Any) -> dict[str, int]:
    tables = (
        "paper_intents",
        "paper_orders",
        "paper_fills",
        "paper_positions",
        "live_orders",
        "positions",
        "shadow_orders",
        "paper_eligibility_candidates",
        "fresh_candidate_seeds",
        "market_link_candidates",
    )
    out: dict[str, int] = {}
    for table in tables:
        if _table_exists(conn, table):
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
            out[table] = int((row or {}).get("count") or 0)
    return out


def _trading_mutation(before: dict[str, int], after: dict[str, int]) -> bool:
    watched = {"paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "positions", "shadow_orders"}
    return any(after.get(table, 0) != before.get(table, 0) for table in watched)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row.get("reg"))


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(part) for key, part in value.items()}
    if isinstance(value, list):
        return [_jsonable(part) for part in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out
