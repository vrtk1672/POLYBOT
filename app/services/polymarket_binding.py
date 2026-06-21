from __future__ import annotations

import json
import os
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.source_status import DEFAULT_CLOB_BASE_URL
from app.services.system_power import SystemPowerService
from app.services.trusted_orderbook import FRESHNESS_SECONDS, MAX_SPREAD, MIN_LIQUIDITY_SCORE


TRUSTED_LINK_CONFIDENCE = 0.8


class PolymarketIdentityBindingService:
    """Recover deterministic Polymarket condition/outcome-token bindings for candidates."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        http_client: Any | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._http = http_client or _PolymarketBindingHttpClient()
        self._snapshotter = OrderbookSnapshotter(connection_factory=self._factory)
        self._orderbooks = OrderbookSnapshotRepository()

    def run_recovery(
        self,
        *,
        cycle_id: str | None = None,
        limit: int = 100,
        refresh_orderbooks: bool = True,
        apply_backfill: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"polymarket_binding_{uuid4().hex}"
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        if system_power != "ON" or not bool(power.get("runtime_work_allowed")):
            payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, "SYSTEM_POWER_OFF")
            self._record_run(payload)
            return _json_safe(payload)
        if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
            payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, "STATE_GOVERNOR_BLOCKED_INTELLIGENCE")
            self._record_run(payload)
            return _json_safe(payload)

        before = self._counts()
        safety_before = self._safety_counts()
        traces: list[dict[str, Any]] = []
        blocker_counts: Counter[str] = Counter()
        market_backfilled = 0
        side_backfilled = 0
        identity_backfilled = 0
        expected_tokens = 0
        clob_attempts = 0
        snapshots_created = 0
        trusted_created = 0
        trusted_refreshed = 0
        rejected = 0
        errors: list[str] = []

        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                candidates = self._load_candidates(conn, limit=limit)
                for candidate in candidates:
                    try:
                        result = self._process_candidate(
                            conn,
                            candidate,
                            run_id=run_id,
                            refresh_orderbooks=refresh_orderbooks,
                            apply_backfill=apply_backfill,
                        )
                        traces.append(result["trace"])
                        blocker_counts[str(result["trace"]["exact_fix_category"])] += 1
                        market_backfilled += int(bool(result.get("market_id_backfilled")))
                        side_backfilled += int(bool(result.get("side_backfilled")))
                        identity_backfilled += int(bool(result.get("market_identity_backfilled")))
                        expected_tokens += int(bool(result.get("expected_token_resolved")))
                        clob_attempts += int(bool(result.get("clob_attempted")))
                        snapshots_created += int(bool(result.get("snapshot_created")))
                        trusted_created += int(bool(result.get("trusted_created")))
                        trusted_refreshed += int(bool(result.get("trusted_refreshed")))
                        rejected += int(not bool(result.get("trusted")))
                    except Exception as exc:
                        rejected += 1
                        blocker_counts["OTHER"] += 1
                        errors.append(f"{candidate.get('eligibility_id') or 'unknown'}:{type(exc).__name__}:{exc}")
                self._record_traces(conn, traces)

        after = self._counts()
        safety_after = self._safety_counts()
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "DEGRADED" if errors else "OK",
            "candidates_checked": len(traces),
            "market_ids_backfilled": market_backfilled,
            "sides_backfilled": side_backfilled,
            "market_identity_backfilled": identity_backfilled,
            "expected_tokens_resolved": expected_tokens,
            "clob_books_attempted": clob_attempts,
            "orderbook_snapshots_created": snapshots_created,
            "trusted_links_created": trusted_created,
            "trusted_links_refreshed": trusted_refreshed,
            "rejected_count": rejected,
            "blocker_counts": dict(blocker_counts),
            "trace_count": len(traces),
            "live_orders_delta": max(0, safety_after["live_orders"] - safety_before["live_orders"]),
            "real_orders_delta": max(0, safety_after["real_orders"] - safety_before["real_orders"]),
            "metadata": {
                "apply_backfill": apply_backfill,
                "refresh_orderbooks": refresh_orderbooks,
                "read_only_clob_book_endpoint": True,
                "no_trading_mutation": True,
                "before": before,
                "after": after,
            },
            "error_message": "; ".join(errors[:10]) if errors else None,
            "before": before,
            "after": after,
            "sample_traces": traces[: min(len(traces), 20)],
        }
        self._record_run(payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 100) -> dict[str, Any]:
        counts = self._counts()
        blocker_counts = self._blocker_counts()
        latest = self._latest_run()
        latest_run_id = latest.get("run_id") if latest else None
        return {
            "mock_data": False,
            "status": "OK",
            "total_candidates": counts["total_candidates"],
            "candidates_with_market_id": counts["candidates_with_market_id"],
            "candidates_with_condition_id": counts["candidates_with_condition_id"],
            "candidates_with_side": counts["candidates_with_side"],
            "candidates_with_yes_no_tokens": counts["candidates_with_yes_no_tokens"],
            "candidates_with_expected_token": counts["candidates_with_expected_token"],
            "candidates_with_clob_book": counts["candidates_with_clob_book"],
            "candidates_with_fresh_orderbook": counts["candidates_with_fresh_orderbook"],
            "candidates_with_trusted_orderbook": counts["candidates_with_trusted_orderbook"],
            "blocker_counts": blocker_counts,
            "top_missing_market_candidates": self._trace_or_live_samples("NO_MARKET_ID", latest_run_id, limit=limit),
            "top_missing_token_candidates": self._trace_or_live_samples("EXPECTED_TOKEN_MISSING", latest_run_id, limit=limit),
            "top_clob_no_book_candidates": self._trace_or_live_samples("CLOB_NO_BOOK", latest_run_id, limit=limit),
            "latest_recovery_run": latest,
            "sample_traces": self._latest_traces(limit=limit),
            "safety_counts": self._extended_safety_counts(),
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _process_candidate(
        self,
        conn: Any,
        candidate: dict[str, Any],
        *,
        run_id: str,
        refresh_orderbooks: bool,
        apply_backfill: bool,
    ) -> dict[str, Any]:
        candidate_id = str(candidate["eligibility_id"])
        signal_ids = _json_list(candidate.get("signal_ids"))
        source_signal_id = signal_ids[0] if signal_ids else None
        current_blockers = sorted(set(_json_list(candidate.get("eligibility_blockers")) + _json_list(candidate.get("missing_requirements"))))
        link_options = self._link_options(conn, signal_ids=signal_ids)
        market_id = _clean(candidate.get("market_id"))
        side = _valid_side(candidate.get("side"))
        market_id_backfilled = False
        side_backfilled = False

        if not market_id:
            resolved_market = _single_value([_clean(row.get("market_id")) for row in link_options])
            if resolved_market:
                market_id = resolved_market
                market_id_backfilled = self._update_candidate_market(conn, candidate_id, market_id) if apply_backfill else False

        if not side:
            resolved_side = _single_value([_valid_side(row.get("matched_side") or (row.get("link_evidence_json") or {}).get("matched_side")) for row in link_options])
            if resolved_side:
                side = resolved_side
                side_backfilled = self._update_candidate_side(conn, candidate_id, side) if apply_backfill else False

        market = self._load_market(conn, market_id) if market_id else None
        identity_backfilled = False
        if market_id and _market_identity_missing(market):
            identity = self._snapshot_identity(conn, market_id=market_id)
            if identity:
                market = self._upsert_market_identity(conn, market=market, identity=identity)
                identity_backfilled = True

        condition_id = _clean((market or {}).get("condition_id"))
        yes_token = _clean((market or {}).get("yes_token_id"))
        no_token = _clean((market or {}).get("no_token_id"))
        expected_token = yes_token if side == "YES" else no_token if side == "NO" else None
        link = self._best_link_for(conn, market_id=market_id, side=side, signal_ids=signal_ids)
        clob_status = "NOT_ATTEMPTED"
        clob_attempted = False
        snapshot_id: int | None = None
        snapshot_ref: str | None = None
        trusted = False
        trusted_created = False
        trusted_refreshed = False
        book_metrics: dict[str, Any] = {}
        exact_category = "UNCHANGED"
        evidence: dict[str, Any] = {
            "source": "polymarket_identity_binding",
            "market_id_backfilled": market_id_backfilled,
            "side_backfilled": side_backfilled,
            "market_identity_backfilled": identity_backfilled,
        }

        if not market_id:
            exact_category = "NO_MARKET_ID"
        elif not condition_id:
            exact_category = "NO_CONDITION_ID"
        elif side not in {"YES", "NO"}:
            exact_category = "NO_SIDE"
        elif not yes_token or not no_token or yes_token == no_token:
            exact_category = "NO_YES_NO_TOKEN_MAPPING"
        elif not expected_token:
            exact_category = "EXPECTED_TOKEN_MISSING"
        elif _market_closed(market):
            exact_category = "MARKET_CLOSED"
        elif _accepting_orders_false(market):
            exact_category = "ACCEPTING_ORDERS_FALSE"
        elif refresh_orderbooks:
            clob_attempted = True
            book = self._fetch_expected_book(expected_token)
            clob_status = book["status"]
            evidence["clob_validation"] = book
            if book["status"] == "OK":
                raw = book["raw"]
                book_market = _clean(raw.get("market"))
                if condition_id and book_market != condition_id:
                    clob_status = "CONDITION_ID_MISMATCH"
                    exact_category = "CONDITION_ID_MISMATCH"
                    evidence["clob_validation"] = {**book, "raw": None, "book_market": book_market, "expected_condition_id": condition_id}
                    trace = {
                        "run_id": run_id,
                        "candidate_id": candidate_id,
                        "source_signal_id": source_signal_id,
                        "market_id": market_id,
                        "slug": (market or {}).get("slug"),
                        "question": (market or {}).get("question"),
                        "condition_id": condition_id,
                        "side": side,
                        "token_id": expected_token,
                        "yes_token_id": yes_token,
                        "no_token_id": no_token,
                        "expected_token_id": expected_token,
                        "current_blockers_json": current_blockers,
                        "candidate_source": _candidate_source(candidate),
                        "gamma_market_match_found": bool(market),
                        "clob_token_book_check_attempted": clob_attempted,
                        "clob_book_status": clob_status,
                        "best_bid": None,
                        "best_ask": None,
                        "spread": None,
                        "snapshot_id": None,
                        "trust_link_id": None,
                        "exact_fix_category": exact_category,
                        "evidence_json": evidence,
                    }
                    return {
                        "trace": trace,
                        "market_id_backfilled": market_id_backfilled,
                        "side_backfilled": side_backfilled,
                        "market_identity_backfilled": identity_backfilled,
                        "expected_token_resolved": bool(expected_token),
                        "clob_attempted": clob_attempted,
                        "snapshot_created": False,
                        "trusted": False,
                        "trusted_created": False,
                        "trusted_refreshed": False,
                    }
                snapshot = self._snapshotter.normalize_orderbook(
                    raw,
                    market_id=market_id,
                    token_id=expected_token,
                    side=side,
                    source="polymarket_binding_recovery",
                    correlation_id=run_id,
                    raw_payload_ref=f"clob:/book:{expected_token}:{datetime.now(UTC).isoformat()}",
                    collected_at=datetime.now(UTC),
                    freshness_window_seconds=FRESHNESS_SECONDS,
                )
                self._orderbooks.append_snapshot(conn, snapshot)
                row = conn.execute(
                    "SELECT * FROM orderbook_snapshots WHERE orderbook_snapshot_id = %s",
                    (snapshot.orderbook_snapshot_id,),
                ).fetchone()
                snapshot_id = int(row["id"]) if row else None
                snapshot_ref = snapshot.orderbook_snapshot_id
                book_metrics = {
                    "best_bid": snapshot.best_bid,
                    "best_ask": snapshot.best_ask,
                    "mid_price": snapshot.mid_price,
                    "spread": snapshot.spread,
                    "liquidity_score": snapshot.liquidity_score,
                    "snapshot_status": snapshot.snapshot_status,
                }
                trust_result = self._trust_result(
                    candidate_id=candidate_id,
                    market_id=market_id,
                    side=side,
                    expected_token=expected_token,
                    snapshot_id=snapshot_id,
                    snapshot_ref=snapshot_ref,
                    token_id=snapshot.token_id,
                    link=link,
                    metrics=book_metrics,
                )
                trusted = bool(trust_result["trusted"])
                exact_category = str(trust_result["trust_reason"] if not trusted else "TRUSTED_ORDERBOOK_CREATED")
                was_created = self._upsert_trusted_link(conn, trust_result)
                if trusted:
                    trusted_created = was_created
                    trusted_refreshed = not was_created
                    self._attach_trusted_orderbook(conn, trust_result)
            else:
                exact_category = clob_status
        else:
            exact_category = "EXPECTED_TOKEN_READY"

        trace = {
            "run_id": run_id,
            "candidate_id": candidate_id,
            "source_signal_id": source_signal_id,
            "market_id": market_id,
            "slug": (market or {}).get("slug"),
            "question": (market or {}).get("question"),
            "condition_id": condition_id,
            "side": side,
            "token_id": expected_token,
            "yes_token_id": yes_token,
            "no_token_id": no_token,
            "expected_token_id": expected_token,
            "current_blockers_json": current_blockers,
            "candidate_source": _candidate_source(candidate),
            "gamma_market_match_found": bool(market),
            "clob_token_book_check_attempted": clob_attempted,
            "clob_book_status": clob_status,
            "best_bid": book_metrics.get("best_bid"),
            "best_ask": book_metrics.get("best_ask"),
            "spread": book_metrics.get("spread"),
            "snapshot_id": snapshot_id,
            "trust_link_id": f"trusted_orderbook_{candidate_id}" if trusted else None,
            "exact_fix_category": exact_category,
            "evidence_json": evidence,
        }
        return {
            "trace": trace,
            "market_id_backfilled": market_id_backfilled,
            "side_backfilled": side_backfilled,
            "market_identity_backfilled": identity_backfilled,
            "expected_token_resolved": bool(expected_token),
            "clob_attempted": clob_attempted,
            "snapshot_created": bool(snapshot_id),
            "trusted": trusted,
            "trusted_created": trusted_created,
            "trusted_refreshed": trusted_refreshed,
        }

    def _load_candidates(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM paper_eligibility_candidates
            WHERE is_runtime_generated = true
              AND COALESCE(is_dry_run_generated, false) = false
              AND (
                    COALESCE(eligibility_blockers, '[]'::jsonb) ?| ARRAY[
                        'MISSING_MARKET_ID','MISSING_SIDE','MISSING_FRESH_ORDERBOOK','MISSING_TRUSTED_ORDERBOOK','MISSING_SIGNAL_MARKET_BINDING'
                    ]
                    OR market_id IS NULL
                    OR side IS NULL
                    OR orderbook_snapshot_id IS NULL
              )
            ORDER BY
                CASE
                    WHEN market_id IS NOT NULL
                     AND market_id <> ''
                     AND side IN ('YES','NO')
                     AND COALESCE(eligibility_blockers, '[]'::jsonb) @> '["MISSING_FRESH_ORDERBOOK"]'::jsonb
                    THEN 0 ELSE 1
                END,
                CASE WHEN COALESCE(eligibility_blockers, '[]'::jsonb) @> '["MISSING_MARKET_ID"]'::jsonb THEN 0 ELSE 1 END,
                CASE WHEN COALESCE(eligibility_blockers, '[]'::jsonb) @> '["MISSING_SIDE"]'::jsonb THEN 0 ELSE 1 END,
                updated_at DESC NULLS LAST,
                id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _link_options(self, conn: Any, *, signal_ids: list[str]) -> list[dict[str, Any]]:
        if not signal_ids:
            return []
        rows = conn.execute(
            """
            SELECT sml.*, nsb.id AS neuron_signal_binding_id
            FROM signal_market_links sml
            LEFT JOIN neuron_signal_bindings nsb ON nsb.signal_id = sml.signal_id AND nsb.market_id = sml.market_id
            WHERE sml.signal_id = ANY(%s)
              AND sml.market_id IS NOT NULL
              AND sml.link_status IN ('confirmed','suggested')
              AND COALESCE(sml.is_review_required, false) = false
              AND COALESCE(sml.link_confidence, sml.confidence, 0) >= %s
            ORDER BY COALESCE(sml.link_confidence, sml.confidence, 0) DESC, sml.id DESC
            """,
            (signal_ids, TRUSTED_LINK_CONFIDENCE),
        ).fetchall()
        return [dict(row) for row in rows]

    def _best_link_for(self, conn: Any, *, market_id: str | None, side: str | None, signal_ids: list[str]) -> dict[str, Any] | None:
        if not market_id or not side or not signal_ids:
            return None
        row = conn.execute(
            """
            SELECT sml.*, nsb.id AS neuron_signal_binding_id
            FROM signal_market_links sml
            LEFT JOIN neuron_signal_bindings nsb ON nsb.signal_id = sml.signal_id AND nsb.market_id = sml.market_id
            WHERE sml.signal_id = ANY(%s)
              AND sml.market_id = %s
              AND sml.matched_side = %s
              AND sml.link_status IN ('confirmed','suggested')
              AND COALESCE(sml.is_review_required, false) = false
              AND COALESCE(sml.link_confidence, sml.confidence, 0) >= %s
            ORDER BY COALESCE(sml.link_confidence, sml.confidence, 0) DESC, sml.id DESC
            LIMIT 1
            """,
            (signal_ids, market_id, side, TRUSTED_LINK_CONFIDENCE),
        ).fetchone()
        return dict(row) if row else None

    def _load_market(self, conn: Any, market_id: str | None) -> dict[str, Any] | None:
        if not market_id:
            return None
        row = conn.execute("SELECT * FROM markets_v2 WHERE market_id = %s", (market_id,)).fetchone()
        return dict(row) if row else None

    def _snapshot_identity(self, conn: Any, *, market_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT market_id, question, slug, accepting_orders, raw_payload AS raw, captured_at AS seen_at
            FROM market_snapshots
            WHERE market_id = %s
              AND raw_payload IS NOT NULL
              AND raw_payload <> '{}'::jsonb
            ORDER BY captured_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()
        if not row:
            row = conn.execute(
                """
                SELECT market_id, NULL::text AS question, NULL::text AS slug, accepting_orders, raw_snapshot_json AS raw, snapshot_at AS seen_at
                FROM market_snapshots_v2
                WHERE market_id = %s
                  AND raw_snapshot_json IS NOT NULL
                  AND raw_snapshot_json <> '{}'::jsonb
                ORDER BY snapshot_at DESC, id DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
        if not row:
            return None
        raw = row["raw"] or {}
        tokens = _yes_no_tokens(raw)
        if not tokens:
            return None
        return {
            "market_id": market_id,
            "condition_id": _clean(raw.get("conditionId") or raw.get("condition_id")),
            "question": _clean(row.get("question") or raw.get("question")),
            "slug": _clean(row.get("slug") or raw.get("slug")),
            "yes_token_id": tokens.get("YES"),
            "no_token_id": tokens.get("NO"),
            "outcome_tokens_json": tokens,
            "accepting_orders": _bool_or_none(raw.get("acceptingOrders") if "acceptingOrders" in raw else row.get("accepting_orders")),
            "closed": bool(raw.get("closed", False)),
            "archived": bool(raw.get("archived", False)),
            "active": bool(raw.get("active", True)),
            "raw_market_json": raw,
            "metadata_json": {
                "identity_recovered_from": "market_snapshots",
                "enable_order_book": _bool_or_none(raw.get("enableOrderBook")),
                "seen_at": _iso(row.get("seen_at")),
            },
        }

    def _upsert_market_identity(self, conn: Any, *, market: dict[str, Any] | None, identity: dict[str, Any]) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, condition_id, question, slug, yes_token_id, no_token_id,
                outcome_tokens_json, accepting_orders, closed, archived, active,
                raw_market_json, metadata_json, resolution_source, source
            )
            VALUES (
                %(market_id)s, %(condition_id)s, %(question)s, %(slug)s,
                %(yes_token_id)s, %(no_token_id)s, %(outcome_tokens_json)s,
                %(accepting_orders)s, %(closed)s, %(archived)s, %(active)s,
                %(raw_market_json)s, %(metadata_json)s, 'polymarket_gamma_snapshot', 'polymarket_gamma'
            )
            ON CONFLICT (market_id) DO UPDATE SET
                condition_id = COALESCE(markets_v2.condition_id, EXCLUDED.condition_id),
                question = COALESCE(markets_v2.question, EXCLUDED.question),
                slug = COALESCE(markets_v2.slug, EXCLUDED.slug),
                yes_token_id = COALESCE(markets_v2.yes_token_id, EXCLUDED.yes_token_id),
                no_token_id = COALESCE(markets_v2.no_token_id, EXCLUDED.no_token_id),
                outcome_tokens_json = CASE
                    WHEN markets_v2.outcome_tokens_json IS NULL OR markets_v2.outcome_tokens_json = '{}'::jsonb THEN EXCLUDED.outcome_tokens_json
                    ELSE markets_v2.outcome_tokens_json
                END,
                accepting_orders = COALESCE(markets_v2.accepting_orders, EXCLUDED.accepting_orders),
                closed = COALESCE(markets_v2.closed, EXCLUDED.closed),
                archived = COALESCE(markets_v2.archived, EXCLUDED.archived),
                active = COALESCE(markets_v2.active, EXCLUDED.active),
                raw_market_json = CASE
                    WHEN markets_v2.raw_market_json IS NULL OR markets_v2.raw_market_json = '{}'::jsonb THEN EXCLUDED.raw_market_json
                    ELSE markets_v2.raw_market_json
                END,
                metadata_json = COALESCE(markets_v2.metadata_json, '{}'::jsonb) || EXCLUDED.metadata_json,
                updated_at = now()
            RETURNING *
            """,
            {
                **identity,
                "outcome_tokens_json": Jsonb(identity["outcome_tokens_json"]),
                "raw_market_json": Jsonb(identity["raw_market_json"]),
                "metadata_json": Jsonb(identity["metadata_json"]),
            },
        ).fetchone()
        return dict(row)

    def _update_candidate_market(self, conn: Any, candidate_id: str, market_id: str) -> bool:
        row = conn.execute(
            """
            UPDATE paper_eligibility_candidates
            SET market_id = %s,
                eligibility_blockers = _jsonb_without_codes(COALESCE(eligibility_blockers, '[]'::jsonb), ARRAY['MISSING_MARKET_ID','MISSING_SIGNAL_MARKET_BINDING']),
                missing_requirements = _jsonb_without_codes(COALESCE(missing_requirements, '[]'::jsonb), ARRAY['MISSING_MARKET_ID','MISSING_SIGNAL_MARKET_BINDING']),
                evidence = COALESCE(evidence, '{}'::jsonb) || %s,
                updated_at = now()
            WHERE eligibility_id = %s
              AND (market_id IS NULL OR market_id = '')
            RETURNING eligibility_id
            """,
            (market_id, Jsonb({"polymarket_binding": {"market_id": market_id, "source": "deterministic_signal_market_link"}}), candidate_id),
        ).fetchone()
        return bool(row)

    def _update_candidate_side(self, conn: Any, candidate_id: str, side: str) -> bool:
        row = conn.execute(
            """
            UPDATE paper_eligibility_candidates
            SET side = %s,
                eligibility_blockers = _jsonb_without_codes(COALESCE(eligibility_blockers, '[]'::jsonb), ARRAY['MISSING_SIDE']),
                missing_requirements = _jsonb_without_codes(COALESCE(missing_requirements, '[]'::jsonb), ARRAY['MISSING_SIDE']),
                evidence = COALESCE(evidence, '{}'::jsonb) || %s,
                updated_at = now()
            WHERE eligibility_id = %s
              AND (side IS NULL OR side NOT IN ('YES','NO'))
            RETURNING eligibility_id
            """,
            (side, Jsonb({"polymarket_binding": {"side": side, "source": "deterministic_signal_market_link"}}), candidate_id),
        ).fetchone()
        return bool(row)

    def _fetch_expected_book(self, token_id: str) -> dict[str, Any]:
        endpoint = f"{(os.getenv('POLYMARKET_CLOB_HOST') or DEFAULT_CLOB_BASE_URL).rstrip('/')}/book"
        started = time.perf_counter()
        try:
            raw, latency_ms = self._http.get_json(endpoint, params={"token_id": token_id})
        except httpx.HTTPStatusError as exc:
            status = "TOKEN_NOT_FOUND" if exc.response.status_code == 404 else "NETWORK_ERROR"
            return {"status": status, "latency_ms": int((time.perf_counter() - started) * 1000), "error_type": type(exc).__name__}
        except Exception as exc:
            text = str(exc)
            status = "CLOB_NO_BOOK" if "orderbook" in text.lower() or "token" in text.lower() else "NETWORK_ERROR"
            return {"status": status, "latency_ms": int((time.perf_counter() - started) * 1000), "error_type": type(exc).__name__, "error_summary": text[:160]}
        latency = latency_ms if latency_ms is not None else int((time.perf_counter() - started) * 1000)
        if not isinstance(raw, dict) or not raw:
            return {"status": "CLOB_NO_BOOK", "latency_ms": latency}
        if _clean(raw.get("asset_id")) != token_id:
            return {"status": "TOKEN_MISMATCH", "latency_ms": latency, "asset_id": raw.get("asset_id")}
        bids = raw.get("bids") or raw.get("buy") or []
        asks = raw.get("asks") or raw.get("sell") or []
        if not bids or not asks:
            return {"status": "CLOB_NO_BOOK", "latency_ms": latency, "asset_id": raw.get("asset_id"), "market": raw.get("market")}
        return {"status": "OK", "latency_ms": latency, "raw": raw, "asset_id": raw.get("asset_id"), "market": raw.get("market")}

    def _trust_result(
        self,
        *,
        candidate_id: str,
        market_id: str,
        side: str,
        expected_token: str,
        snapshot_id: int | None,
        snapshot_ref: str | None,
        token_id: str | None,
        link: dict[str, Any] | None,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        spread = _float_or_none(metrics.get("spread"))
        liquidity = _float_or_none(metrics.get("liquidity_score"))
        status = str(metrics.get("snapshot_status") or "")
        trusted = (
            snapshot_id is not None
            and token_id == expected_token
            and status == "OK"
            and spread is not None
            and spread <= MAX_SPREAD
            and (liquidity is None or liquidity >= MIN_LIQUIDITY_SCORE)
        )
        reason = "TRUSTED_ORDERBOOK"
        if token_id != expected_token:
            reason = "TOKEN_MISMATCH"
        elif status != "OK":
            reason = "CLOB_NO_BOOK"
        elif spread is None:
            reason = "MISSING_SPREAD"
        elif spread > MAX_SPREAD:
            reason = "SPREAD_TOO_WIDE"
        elif liquidity is not None and liquidity < MIN_LIQUIDITY_SCORE:
            reason = "LIQUIDITY_TOO_LOW"
        return {
            "link_id": f"trusted_orderbook_{candidate_id}",
            "candidate_id": candidate_id,
            "market_id": market_id,
            "side": side,
            "expected_token_id": expected_token,
            "orderbook_snapshot_id": snapshot_id,
            "orderbook_snapshot_ref": snapshot_ref,
            "orderbook_token_id": token_id,
            "trusted": trusted,
            "trust_status": "TRUSTED" if trusted else "REJECTED",
            "trust_reason": reason,
            "best_bid": metrics.get("best_bid"),
            "best_ask": metrics.get("best_ask"),
            "mid_price": metrics.get("mid_price"),
            "spread": spread,
            "liquidity_score": liquidity,
            "age_seconds": 0,
            "freshness_threshold_seconds": FRESHNESS_SECONDS,
            "signal_market_link_id": (link or {}).get("id"),
            "neuron_signal_binding_id": (link or {}).get("neuron_signal_binding_id"),
            "evidence_json": {
                "source": "polymarket_identity_binding",
                "validated_asset_id": True,
                "validated_condition_id": True,
            },
        }

    def _upsert_trusted_link(self, conn: Any, result: dict[str, Any]) -> bool:
        existing = conn.execute("SELECT 1 FROM trusted_orderbook_evidence_links WHERE candidate_id = %s", (result["candidate_id"],)).fetchone()
        conn.execute(
            """
            INSERT INTO trusted_orderbook_evidence_links (
                link_id, candidate_id, market_id, side, expected_token_id,
                orderbook_snapshot_id, orderbook_snapshot_ref, orderbook_token_id,
                trusted, trust_status, trust_reason, best_bid, best_ask,
                mid_price, spread, liquidity_score, age_seconds,
                freshness_threshold_seconds, signal_market_link_id,
                neuron_signal_binding_id, evidence_json, created_at, updated_at
            )
            VALUES (
                %(link_id)s, %(candidate_id)s, %(market_id)s, %(side)s,
                %(expected_token_id)s, %(orderbook_snapshot_id)s,
                %(orderbook_snapshot_ref)s, %(orderbook_token_id)s,
                %(trusted)s, %(trust_status)s, %(trust_reason)s, %(best_bid)s,
                %(best_ask)s, %(mid_price)s, %(spread)s, %(liquidity_score)s,
                %(age_seconds)s, %(freshness_threshold_seconds)s,
                %(signal_market_link_id)s, %(neuron_signal_binding_id)s,
                %(evidence_json)s, now(), now()
            )
            ON CONFLICT (candidate_id) DO UPDATE SET
                market_id = EXCLUDED.market_id,
                side = EXCLUDED.side,
                expected_token_id = EXCLUDED.expected_token_id,
                orderbook_snapshot_id = EXCLUDED.orderbook_snapshot_id,
                orderbook_snapshot_ref = EXCLUDED.orderbook_snapshot_ref,
                orderbook_token_id = EXCLUDED.orderbook_token_id,
                trusted = EXCLUDED.trusted,
                trust_status = EXCLUDED.trust_status,
                trust_reason = EXCLUDED.trust_reason,
                best_bid = EXCLUDED.best_bid,
                best_ask = EXCLUDED.best_ask,
                mid_price = EXCLUDED.mid_price,
                spread = EXCLUDED.spread,
                liquidity_score = EXCLUDED.liquidity_score,
                age_seconds = EXCLUDED.age_seconds,
                freshness_threshold_seconds = EXCLUDED.freshness_threshold_seconds,
                signal_market_link_id = EXCLUDED.signal_market_link_id,
                neuron_signal_binding_id = EXCLUDED.neuron_signal_binding_id,
                evidence_json = EXCLUDED.evidence_json,
                updated_at = now()
            """,
            {**result, "evidence_json": Jsonb(_json_safe(result.get("evidence_json") or {}))},
        )
        return existing is None

    def _attach_trusted_orderbook(self, conn: Any, result: dict[str, Any]) -> None:
        conn.execute(
            """
            UPDATE paper_eligibility_candidates
            SET orderbook_snapshot_id = %s,
                evidence = COALESCE(evidence, '{}'::jsonb) || %s,
                eligibility_blockers = _jsonb_without_codes(COALESCE(eligibility_blockers, '[]'::jsonb), ARRAY['MISSING_TRUSTED_ORDERBOOK','MISSING_FRESH_ORDERBOOK']),
                missing_requirements = _jsonb_without_codes(COALESCE(missing_requirements, '[]'::jsonb), ARRAY['MISSING_TRUSTED_ORDERBOOK','MISSING_FRESH_ORDERBOOK']),
                updated_at = now()
            WHERE eligibility_id = %s
            """,
            (
                result["orderbook_snapshot_id"],
                Jsonb({"trusted_orderbook": {"trusted": True, "source": "polymarket_identity_binding", "expected_token_id": result["expected_token_id"]}}),
                result["candidate_id"],
            ),
        )

    def _record_traces(self, conn: Any, traces: list[dict[str, Any]]) -> None:
        if not traces or not _table_exists(conn, "polymarket_binding_candidate_traces"):
            return
        for trace in traces:
            conn.execute(
                """
                INSERT INTO polymarket_binding_candidate_traces (
                    run_id, candidate_id, source_signal_id, market_id, slug, question,
                    condition_id, side, token_id, yes_token_id, no_token_id, expected_token_id,
                    current_blockers_json, candidate_source, gamma_market_match_found,
                    clob_token_book_check_attempted, clob_book_status, best_bid, best_ask,
                    spread, snapshot_id, trust_link_id, exact_fix_category, evidence_json
                )
                VALUES (
                    %(run_id)s, %(candidate_id)s, %(source_signal_id)s, %(market_id)s,
                    %(slug)s, %(question)s, %(condition_id)s, %(side)s, %(token_id)s,
                    %(yes_token_id)s, %(no_token_id)s, %(expected_token_id)s,
                    %(current_blockers_json)s, %(candidate_source)s, %(gamma_market_match_found)s,
                    %(clob_token_book_check_attempted)s, %(clob_book_status)s,
                    %(best_bid)s, %(best_ask)s, %(spread)s, %(snapshot_id)s,
                    %(trust_link_id)s, %(exact_fix_category)s, %(evidence_json)s
                )
                ON CONFLICT (run_id, candidate_id) DO NOTHING
                """,
                {
                    **trace,
                    "current_blockers_json": Jsonb(trace.get("current_blockers_json") or []),
                    "evidence_json": Jsonb(_json_safe(trace.get("evidence_json") or {})),
                },
            )

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "polymarket_binding_recovery_runs"):
                return
            conn.execute(
                """
                INSERT INTO polymarket_binding_recovery_runs (
                    run_id, cycle_id, system_power, started_at, finished_at, status,
                    candidates_checked, market_ids_backfilled, sides_backfilled,
                    market_identity_backfilled, expected_tokens_resolved,
                    clob_books_attempted, orderbook_snapshots_created,
                    trusted_links_created, trusted_links_refreshed, rejected_count,
                    blocker_counts_json, trace_count, live_orders_delta, real_orders_delta,
                    metadata_json, error_message
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(system_power)s, %(started_at)s,
                    %(finished_at)s, %(status)s, %(candidates_checked)s,
                    %(market_ids_backfilled)s, %(sides_backfilled)s,
                    %(market_identity_backfilled)s, %(expected_tokens_resolved)s,
                    %(clob_books_attempted)s, %(orderbook_snapshots_created)s,
                    %(trusted_links_created)s, %(trusted_links_refreshed)s,
                    %(rejected_count)s, %(blocker_counts_json)s, %(trace_count)s,
                    %(live_orders_delta)s, %(real_orders_delta)s, %(metadata_json)s,
                    %(error_message)s
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                {
                    **payload,
                    "blocker_counts_json": Jsonb(_json_safe(payload.get("blocker_counts") or {})),
                    "metadata_json": Jsonb(_json_safe(payload.get("metadata") or {})),
                },
            )

    def _blocked_payload(self, run_id: str, cycle_id: str | None, system_power: str, started_at: datetime, reason: str) -> dict[str, Any]:
        counts = self._counts()
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "BLOCKED",
            "candidates_checked": 0,
            "market_ids_backfilled": 0,
            "sides_backfilled": 0,
            "market_identity_backfilled": 0,
            "expected_tokens_resolved": 0,
            "clob_books_attempted": 0,
            "orderbook_snapshots_created": 0,
            "trusted_links_created": 0,
            "trusted_links_refreshed": 0,
            "rejected_count": 0,
            "blocker_counts": {reason: 1},
            "trace_count": 0,
            "live_orders_delta": 0,
            "real_orders_delta": 0,
            "metadata": {"reason": reason, "counts": counts},
            "error_message": reason,
        }

    def _counts(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {}
        with self._factory.connect() as conn:
            return _binding_counts(conn)

    def _blocker_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {}
        with self._factory.connect() as conn:
            return _binding_blockers(conn)

    def _latest_run(self) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "polymarket_binding_recovery_runs"):
                return None
            row = conn.execute("SELECT * FROM polymarket_binding_recovery_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _latest_traces(self, *, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "polymarket_binding_candidate_traces"):
                return []
            rows = conn.execute(
                """
                SELECT *
                FROM polymarket_binding_candidate_traces
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _trace_or_live_samples(self, category: str, run_id: str | None, *, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if run_id and _table_exists(conn, "polymarket_binding_candidate_traces"):
                rows = conn.execute(
                    """
                    SELECT *
                    FROM polymarket_binding_candidate_traces
                    WHERE run_id = %s AND exact_fix_category = %s
                    ORDER BY id
                    LIMIT %s
                    """,
                    (run_id, category, limit),
                ).fetchall()
                if rows:
                    return [_json_safe(dict(row)) for row in rows]
            rows = conn.execute(
                """
                SELECT eligibility_id AS candidate_id, market_id, side, eligibility_blockers, missing_requirements
                FROM paper_eligibility_candidates
                WHERE COALESCE(eligibility_blockers, '[]'::jsonb) @> %s::jsonb
                ORDER BY updated_at DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (json.dumps([_legacy_code_for_category(category)]), limit),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _safety_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {"live_orders": 0, "real_orders": 0}
        with self._factory.connect() as conn:
            return {"live_orders": _count_table(conn, "live_orders"), "real_orders": _count_table(conn, "orders_v2")}

    def _extended_safety_counts(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {}
        with self._factory.connect() as conn:
            return {
                "live_orders": _count_table(conn, "live_orders"),
                "paper_intents": _count_table(conn, "paper_intents"),
                "paper_orders": _count_table(conn, "paper_orders"),
                "paper_fills": _count_table(conn, "paper_fills"),
                "paper_positions": _count_table(conn, "paper_positions"),
                "paper_capital_ledger": _count_table(conn, "paper_capital_ledger"),
                "orders_v2": _count_table(conn, "orders_v2"),
                "fills_v2": _count_table(conn, "fills_v2"),
                "canonical_positions": _count_table(conn, "positions"),
            }


class _PolymarketBindingHttpClient:
    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[dict[str, object], int]:
        started = time.perf_counter()
        with httpx.Client(timeout=10.0, headers={"User-Agent": "POLYBOT-polymarket-binding/1.0"}) as client:
            response = client.get(url, params=params)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms


def _binding_counts(conn: Any) -> dict[str, Any]:
    return {
        "total_candidates": _count_table(conn, "paper_eligibility_candidates"),
        "candidates_with_market_id": _count_where(conn, "paper_eligibility_candidates", "market_id IS NOT NULL AND market_id <> ''"),
        "candidates_missing_market_id": _count_where(conn, "paper_eligibility_candidates", "market_id IS NULL OR market_id = ''"),
        "candidates_with_condition_id": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec JOIN markets_v2 m ON m.market_id=pec.market_id WHERE m.condition_id IS NOT NULL AND m.condition_id <> ''"),
        "candidates_missing_condition_id": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec LEFT JOIN markets_v2 m ON m.market_id=pec.market_id WHERE pec.market_id IS NOT NULL AND pec.market_id <> '' AND (m.condition_id IS NULL OR m.condition_id = '')"),
        "candidates_with_side": _count_where(conn, "paper_eligibility_candidates", "side IN ('YES','NO')"),
        "candidates_missing_side": _count_where(conn, "paper_eligibility_candidates", "side IS NULL OR side NOT IN ('YES','NO')"),
        "candidates_with_yes_no_tokens": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec JOIN markets_v2 m ON m.market_id=pec.market_id WHERE m.yes_token_id IS NOT NULL AND m.yes_token_id<>'' AND m.no_token_id IS NOT NULL AND m.no_token_id<>''"),
        "candidates_with_expected_token": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec JOIN markets_v2 m ON m.market_id=pec.market_id WHERE (pec.side='YES' AND m.yes_token_id IS NOT NULL AND m.yes_token_id<>'') OR (pec.side='NO' AND m.no_token_id IS NOT NULL AND m.no_token_id<>'')"),
        "candidates_with_clob_book": _scalar(conn, "SELECT COUNT(DISTINCT pec.eligibility_id) FROM paper_eligibility_candidates pec JOIN markets_v2 m ON m.market_id=pec.market_id JOIN orderbook_snapshots obs ON obs.market_id=pec.market_id AND obs.token_id = CASE WHEN pec.side='YES' THEN m.yes_token_id WHEN pec.side='NO' THEN m.no_token_id ELSE NULL END"),
        "candidates_with_fresh_orderbook": _scalar(conn, "SELECT COUNT(DISTINCT pec.eligibility_id) FROM paper_eligibility_candidates pec JOIN markets_v2 m ON m.market_id=pec.market_id JOIN orderbook_snapshots obs ON obs.market_id=pec.market_id AND obs.token_id = CASE WHEN pec.side='YES' THEN m.yes_token_id WHEN pec.side='NO' THEN m.no_token_id ELSE NULL END WHERE obs.snapshot_status='OK' AND COALESCE(obs.is_stale,false)=false AND COALESCE(obs.snapshot_at,obs.collected_at,obs.created_at) >= now() - interval '180 seconds'"),
        "candidates_with_trusted_orderbook": _count_where(conn, "trusted_orderbook_evidence_links", "trusted = true"),
        "risk_approved": _count_where(conn, "risk_decisions", "risk_approved = true"),
        "exit_ready": _count_where(conn, "exit_plans", "COALESCE(paper_exit_ready, false) = true"),
        "eligible_candidates": _count_where(conn, "paper_eligibility_candidates", "status = 'ELIGIBLE'"),
        "paper_intents": _count_table(conn, "paper_intents"),
        "paper_orders": _count_table(conn, "paper_orders"),
        "paper_fills": _count_table(conn, "paper_fills"),
        "paper_positions": _count_table(conn, "paper_positions"),
        "live_orders": _count_table(conn, "live_orders"),
        "orders_v2": _count_table(conn, "orders_v2"),
        "fills_v2": _count_table(conn, "fills_v2"),
        "canonical_positions": _count_table(conn, "positions"),
    }


def _binding_blockers(conn: Any) -> dict[str, int]:
    return {
        "NO_MARKET_ID": _count_where(conn, "paper_eligibility_candidates", "market_id IS NULL OR market_id = ''"),
        "NO_CONDITION_ID": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec LEFT JOIN markets_v2 m ON m.market_id=pec.market_id WHERE pec.market_id IS NOT NULL AND pec.market_id<>'' AND (m.condition_id IS NULL OR m.condition_id='')"),
        "NO_SIDE": _count_where(conn, "paper_eligibility_candidates", "side IS NULL OR side NOT IN ('YES','NO')"),
        "NO_TOKEN_ID": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec LEFT JOIN markets_v2 m ON m.market_id=pec.market_id WHERE pec.side IN ('YES','NO') AND ((pec.side='YES' AND (m.yes_token_id IS NULL OR m.yes_token_id='')) OR (pec.side='NO' AND (m.no_token_id IS NULL OR m.no_token_id='')))"),
        "NO_YES_NO_TOKEN_MAPPING": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec LEFT JOIN markets_v2 m ON m.market_id=pec.market_id WHERE pec.market_id IS NOT NULL AND pec.market_id<>'' AND (m.yes_token_id IS NULL OR m.no_token_id IS NULL OR m.yes_token_id='' OR m.no_token_id='' OR m.yes_token_id=m.no_token_id)"),
        "EXPECTED_TOKEN_MISSING": _scalar(conn, "SELECT COUNT(*) FROM paper_eligibility_candidates pec LEFT JOIN markets_v2 m ON m.market_id=pec.market_id WHERE pec.side IN ('YES','NO') AND CASE WHEN pec.side='YES' THEN m.yes_token_id WHEN pec.side='NO' THEN m.no_token_id ELSE NULL END IS NULL"),
        "CLOB_NO_BOOK": _count_where(conn, "polymarket_binding_candidate_traces", "exact_fix_category = 'CLOB_NO_BOOK'"),
        "SNAPSHOT_STALE": _count_where(conn, "trusted_orderbook_evidence_links", "trust_reason = 'ORDERBOOK_STALE'"),
        "TOKEN_MISMATCH": _count_where(conn, "trusted_orderbook_evidence_links", "trust_reason IN ('TOKEN_MISMATCH','TOKEN_SIDE_MISMATCH')"),
        "SIDE_MISMATCH": _count_where(conn, "trusted_orderbook_evidence_links", "trust_reason = 'SIDE_MISMATCH'"),
        "MISSING_FRESH_ORDERBOOK": _candidate_code_count(conn, "MISSING_FRESH_ORDERBOOK"),
    }


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def _candidate_code_count(conn: Any, code: str) -> int:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return 0
    return int(conn.execute("SELECT COUNT(*) AS count FROM paper_eligibility_candidates WHERE COALESCE(eligibility_blockers, '[]'::jsonb) @> %s::jsonb", (json.dumps([code]),)).fetchone()["count"] or 0)


def _scalar(conn: Any, sql: str) -> int:
    return int(conn.execute(sql).fetchone()["count"] or 0)


def _legacy_code_for_category(category: str) -> str:
    return {
        "NO_MARKET_ID": "MISSING_MARKET_ID",
        "NO_SIDE": "MISSING_SIDE",
        "CLOB_NO_BOOK": "MISSING_FRESH_ORDERBOOK",
        "EXPECTED_TOKEN_MISSING": "MISSING_FRESH_ORDERBOOK",
    }.get(category, category)


def _single_value(values: list[Any]) -> Any | None:
    clean = [value for value in values if value is not None and value != ""]
    unique = sorted(set(clean))
    return unique[0] if len(unique) == 1 else None


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None]
        except json.JSONDecodeError:
            return []
    return []


def _yes_no_tokens(raw: dict[str, Any]) -> dict[str, str] | None:
    tokens = _parse_jsonish_list(raw.get("clobTokenIds") or raw.get("clob_token_ids") or raw.get("tokenIds"))
    outcomes = [str(item).strip().upper() for item in _parse_jsonish_list(raw.get("outcomes"))]
    if len(tokens) < 2:
        return None
    if outcomes and len(outcomes) >= 2:
        mapping: dict[str, str] = {}
        for outcome, token in zip(outcomes, tokens, strict=False):
            if outcome in {"YES", "NO"}:
                mapping[outcome] = str(token)
        if mapping.get("YES") and mapping.get("NO"):
            return mapping
    return {"YES": str(tokens[0]), "NO": str(tokens[1])}


def _parse_jsonish_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _market_identity_missing(market: dict[str, Any] | None) -> bool:
    if not market:
        return True
    return not _clean(market.get("condition_id")) or not _clean(market.get("yes_token_id")) or not _clean(market.get("no_token_id"))


def _market_closed(market: dict[str, Any] | None) -> bool:
    return bool((market or {}).get("closed")) or bool((market or {}).get("archived")) or (market is not None and (market or {}).get("active") is False)


def _accepting_orders_false(market: dict[str, Any] | None) -> bool:
    return market is not None and (market or {}).get("accepting_orders") is False


def _candidate_source(candidate: dict[str, Any]) -> str:
    producer = str(candidate.get("producer_name") or candidate.get("generated_by") or "")
    if "source_to_neuron" in producer:
        return "source-to-neuron"
    if bool(candidate.get("is_runtime_generated")):
        return "runtime brain"
    if bool(candidate.get("is_dry_run_generated")):
        return "old/stale"
    return "paper eligibility"


def _valid_side(value: Any) -> str | None:
    side = str(value or "").upper()
    return side if side in {"YES", "NO"} else None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in {"true", "1", "yes"}:
            return True
        if value.lower() in {"false", "0", "no"}:
            return False
    return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value
