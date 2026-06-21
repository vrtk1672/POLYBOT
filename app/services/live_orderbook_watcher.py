from __future__ import annotations

import os
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.mesh_sessions.service import MeshSessionService
from app.neural_bus.contracts import NeuralEvent
from app.neural_bus.repository import NeuralEventRepository
from app.neural_bus.types import NeuralEventType
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.security.redaction import redact_secrets
from app.services.fresh_market_identity import SECURITY_GOVERNANCE_STATUS
from app.services.source_status import DEFAULT_CLOB_BASE_URL
from app.services.system_power import SystemPowerService
from app.services.trusted_orderbook import FRESHNESS_SECONDS


SPREAD_ABS_THRESHOLD = 0.005
SPREAD_REL_THRESHOLD = 0.20
LIQUIDITY_ABS_THRESHOLD = 0.10
LIQUIDITY_REL_THRESHOLD = 0.25
MID_PRICE_ABS_THRESHOLD = 0.01
MAX_FAILURES_BEFORE_DEGRADED = 3


class LiveOrderbookWatcherService:
    """Bounded read-only CLOB polling for verified fresh market tokens."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        clob_client: Any | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._clob = clob_client or _WatcherHttpClient()
        self._snapshotter = OrderbookSnapshotter(connection_factory=self._factory)
        self._orderbooks = OrderbookSnapshotRepository()
        self._events = NeuralEventRepository()
        self._mesh = MeshSessionService(connection_factory=self._factory)

    def run(
        self,
        *,
        cycle_id: str | None = None,
        limit: int = 25,
        dry_run: bool = False,
        max_seconds: int = 30,
        include_priority: int = 10,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"live_orderbook_watcher_{uuid4().hex}"
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        if system_power != "ON" or not bool(power.get("runtime_work_allowed")):
            payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, dry_run, "SYSTEM_POWER_OFF")
            self._record_run(payload)
            return _json_safe(payload)
        if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
            payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, dry_run, "STATE_GOVERNOR_BLOCKED_INTELLIGENCE")
            self._record_run(payload)
            return _json_safe(payload)

        before = self._counts()
        safety_before = self._safety_counts()
        blockers: Counter[str] = Counter()
        errors: list[str] = []
        watch_items_checked = 0
        orderbooks_refreshed = 0
        spread_changed = 0
        liquidity_changed = 0
        token_unavailable = 0
        market_resolved = 0
        events_published = 0
        snapshots_created = 0
        deadline = time.perf_counter() + max(1, max_seconds)

        with self._factory.connect() as conn:
            with conn.transaction():
                selected = self._select_watchlist_sources(conn, limit=limit, include_priority=include_priority)
                if not dry_run:
                    for source in selected:
                        self._upsert_watch_item(conn, source)
                watch_items = self._load_watch_items(conn, limit=limit, include_priority=include_priority) if not dry_run else selected
                for item in watch_items:
                    if time.perf_counter() >= deadline:
                        blockers["MAX_SECONDS_EXHAUSTED"] += 1
                        break
                    try:
                        watch_items_checked += 1
                        if dry_run:
                            blockers["DRY_RUN_NOT_POLLED"] += 1
                            continue
                        trace, event_types = self._poll_watch_item(conn, run_id=run_id, item=item)
                        reason = trace.get("reason")
                        for event_type in event_types:
                            if event_type == NeuralEventType.ORDERBOOK_REFRESHED.value:
                                orderbooks_refreshed += 1
                            elif event_type == NeuralEventType.SPREAD_CHANGED.value:
                                spread_changed += 1
                            elif event_type == NeuralEventType.LIQUIDITY_CHANGED.value:
                                liquidity_changed += 1
                            elif event_type == NeuralEventType.TOKEN_BOOK_UNAVAILABLE.value:
                                token_unavailable += 1
                            elif event_type == NeuralEventType.MARKET_RESOLVED.value:
                                market_resolved += 1
                        events_published += len(event_types)
                        snapshots_created += int(bool(trace.get("new_snapshot_id")))
                        blockers[reason or "OK"] += 1
                    except Exception as exc:
                        errors.append(_error_summary(item.get("watch_id"), exc))
                        blockers["ERROR"] += 1
            conn.commit()

        after = self._counts()
        safety_after = self._safety_counts()
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "system_power": system_power,
            "status": "DEGRADED" if errors else "OK",
            "dry_run": dry_run,
            "watch_items_checked": watch_items_checked,
            "orderbooks_refreshed": orderbooks_refreshed,
            "spread_changed_count": spread_changed,
            "liquidity_changed_count": liquidity_changed,
            "token_unavailable_count": token_unavailable,
            "market_resolved_count": market_resolved,
            "events_published": events_published,
            "snapshots_created": snapshots_created,
            "errors_count": len(errors),
            "blocker_counts": dict(blockers),
            "safety_counts_before": safety_before,
            "safety_counts_after": safety_after,
            "live_orders_delta": max(0, safety_after["live_orders"] - safety_before["live_orders"]),
            "real_orders_delta": max(0, safety_after["orders_v2"] - safety_before["orders_v2"]),
            "metadata": {
                "phase": "live_token_orderbook_watcher",
                "bounded_polling": True,
                "max_seconds": max_seconds,
                "include_priority": include_priority,
                "selected_watchlist_sources": len(selected),
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "no_trading_mutation": True,
                "before": before,
                "after": after,
            },
            "error_message": "; ".join(errors[:10]) if errors else None,
            "before": before,
            "after": after,
            "latest_traces": self._latest_traces(limit=20),
        }
        self._record_run(payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 100) -> dict[str, Any]:
        counts = self._counts()
        latest = self._latest_run()
        return {
            "mock_data": False,
            "status": "OK",
            "watchlist_count": counts["watchlist_count"],
            "active_watch_items": counts["active_watch_items"],
            "degraded_watch_items": counts["degraded_watch_items"],
            "token_unavailable_count": counts["token_unavailable_count"],
            "latest_run": latest,
            "events_published": int((latest or {}).get("events_published") or counts["watcher_events"]),
            "orderbooks_refreshed": counts["ORDERBOOK_REFRESHED"],
            "spread_changed_count": counts["SPREAD_CHANGED"],
            "liquidity_changed_count": counts["LIQUIDITY_CHANGED"],
            "top_watch_items": self._top_watch_items(limit=limit),
            "latest_traces": self._latest_traces(limit=limit),
            "security_governance_status": SECURITY_GOVERNANCE_STATUS,
            "safety_counts": self._safety_counts(),
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _select_watchlist_sources(self, conn: Any, *, limit: int, include_priority: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if _table_exists(conn, "fresh_candidate_seeds"):
            rows.extend(dict(row) for row in conn.execute(
                """
                SELECT
                    seed_id AS source_id,
                    'fresh_candidate_seed' AS source_type,
                    market_id,
                    condition_id,
                    side,
                    expected_token_id AS token_id,
                    1 AS priority,
                    status,
                    metadata_json
                FROM fresh_candidate_seeds
                WHERE status = 'BOOK_VERIFIED'
                  AND market_id IS NOT NULL AND market_id <> ''
                  AND condition_id IS NOT NULL AND condition_id <> ''
                  AND expected_token_id IS NOT NULL AND expected_token_id <> ''
                  AND side IN ('YES','NO')
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall())
        if _table_exists(conn, "trusted_orderbook_evidence_links"):
            rows.extend(dict(row) for row in conn.execute(
                """
                SELECT
                    link_id AS source_id,
                    'trusted_orderbook_link' AS source_type,
                    market_id,
                    COALESCE((evidence_json->>'condition_id'), '') AS condition_id,
                    side,
                    expected_token_id AS token_id,
                    2 AS priority,
                    trust_status AS status,
                    evidence_json AS metadata_json
                FROM trusted_orderbook_evidence_links
                WHERE trusted = true
                  AND candidate_id LIKE 'fresh_seed_%%'
                  AND market_id IS NOT NULL AND market_id <> ''
                  AND expected_token_id IS NOT NULL AND expected_token_id <> ''
                  AND side IN ('YES','NO')
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall())
        if _table_exists(conn, "paper_eligibility_candidates") and _table_exists(conn, "markets_v2"):
            rows.extend(dict(row) for row in conn.execute(
                """
                SELECT
                    pec.eligibility_id AS source_id,
                    'fresh_verified_candidate' AS source_type,
                    pec.market_id,
                    m.condition_id,
                    pec.side,
                    pec.expected_token_id AS token_id,
                    3 AS priority,
                    pec.identity_status AS status,
                    pec.evidence AS metadata_json
                FROM paper_eligibility_candidates pec
                JOIN markets_v2 m ON m.market_id = pec.market_id
                WHERE pec.identity_status = 'FRESH_VERIFIED'
                  AND pec.side IN ('YES','NO')
                  AND pec.expected_token_id IS NOT NULL AND pec.expected_token_id <> ''
                  AND m.condition_id IS NOT NULL AND m.condition_id <> ''
                  AND COALESCE(m.closed,false) = false
                  AND COALESCE(m.archived,false) = false
                  AND COALESCE(m.active,true) = true
                  AND COALESCE(m.accepting_orders,true) = true
                ORDER BY pec.identity_verified_at DESC NULLS LAST, pec.updated_at DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            ).fetchall())
        enriched = []
        seen: set[str] = set()
        for row in sorted(rows, key=lambda item: int(item.get("priority") or 10)):
            row = dict(row)
            if row.get("market_id") and _table_exists(conn, "markets_v2"):
                market = conn.execute("SELECT condition_id, closed, archived, active, accepting_orders FROM markets_v2 WHERE market_id=%s", (row["market_id"],)).fetchone()
                if market:
                    row["condition_id"] = row.get("condition_id") or market.get("condition_id")
                    if bool(market.get("closed")) or bool(market.get("archived")) or market.get("active") is False or market.get("accepting_orders") is False:
                        continue
            if not _valid_watch_source(row):
                continue
            if int(row.get("priority") or 10) > include_priority:
                continue
            watch_id = _watch_id(row["market_id"], row["side"], row["token_id"])
            if watch_id in seen:
                continue
            seen.add(watch_id)
            row["watch_id"] = watch_id
            enriched.append(row)
            if len(enriched) >= limit:
                break
        return enriched

    def _upsert_watch_item(self, conn: Any, item: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO live_orderbook_watchlist (
                watch_id, market_id, condition_id, side, token_id, source_type,
                source_id, priority, status, metadata_json, updated_at
            )
            VALUES (
                %(watch_id)s, %(market_id)s, %(condition_id)s, %(side)s,
                %(token_id)s, %(source_type)s, %(source_id)s, %(priority)s,
                'ACTIVE', %(metadata_json)s, now()
            )
            ON CONFLICT (watch_id) DO UPDATE SET
                condition_id=EXCLUDED.condition_id,
                source_type=EXCLUDED.source_type,
                source_id=EXCLUDED.source_id,
                priority=LEAST(live_orderbook_watchlist.priority, EXCLUDED.priority),
                status=CASE WHEN live_orderbook_watchlist.status='DISABLED' THEN 'DISABLED' ELSE 'ACTIVE' END,
                metadata_json=COALESCE(live_orderbook_watchlist.metadata_json,'{}'::jsonb) || EXCLUDED.metadata_json,
                updated_at=now()
            """,
            {**item, "metadata_json": Jsonb(_json_safe(item.get("metadata_json") or {}))},
        )

    def _load_watch_items(self, conn: Any, *, limit: int, include_priority: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM live_orderbook_watchlist
            WHERE status IN ('ACTIVE','DEGRADED','TOKEN_UNAVAILABLE')
              AND priority <= %s
            ORDER BY priority ASC, last_polled_at ASC NULLS FIRST, updated_at DESC
            LIMIT %s
            """,
            (include_priority, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _poll_watch_item(self, conn: Any, *, run_id: str, item: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        if self._market_resolved(conn, item):
            trace = self._insert_trace(conn, run_id=run_id, item=item, clob_status="NOT_ATTEMPTED", reason="MARKET_RESOLVED", metrics={})
            event_types = self._publish_events(conn, trace=trace, event_types=[NeuralEventType.MARKET_RESOLVED.value])
            self._update_watch_failure(conn, item, status="MARKET_RESOLVED", reason="MARKET_RESOLVED")
            self._update_trace_events(conn, trace["id"], event_types)
            trace["events_published_json"] = event_types
            return trace, event_types

        clob = self._fetch_book(str(item["token_id"]))
        if clob["status"] != "OK":
            reason = str(clob["status"])
            trace = self._insert_trace(conn, run_id=run_id, item=item, clob_status=reason, reason=reason, metrics={}, clob=clob)
            event_types = self._publish_events(conn, trace=trace, event_types=[NeuralEventType.TOKEN_BOOK_UNAVAILABLE.value])
            self._update_watch_failure(conn, item, status="TOKEN_UNAVAILABLE" if reason in {"TOKEN_NOT_FOUND", "CLOB_NO_BOOK", "EMPTY_BIDS", "EMPTY_ASKS"} else "DEGRADED", reason=reason)
            self._update_trace_events(conn, trace["id"], event_types)
            trace["events_published_json"] = event_types
            return trace, event_types

        reason = self._validate_book(clob, item)
        if reason:
            trace = self._insert_trace(conn, run_id=run_id, item=item, clob_status="REJECTED", reason=reason, metrics={}, clob=clob)
            event_types = self._publish_events(conn, trace=trace, event_types=[NeuralEventType.TOKEN_BOOK_UNAVAILABLE.value])
            self._update_watch_failure(conn, item, status="DEGRADED", reason=reason)
            self._update_trace_events(conn, trace["id"], event_types)
            trace["events_published_json"] = event_types
            return trace, event_types

        snapshot_id, metrics = self._persist_snapshot(conn, raw=clob["raw"], item=item, run_id=run_id)
        event_types = self._detect_events(item, metrics)
        trace = self._insert_trace(conn, run_id=run_id, item=item, clob_status="OK", reason=None, metrics=metrics, new_snapshot_id=snapshot_id, clob=clob)
        published = self._publish_events(conn, trace=trace, event_types=event_types)
        self._update_watch_success(conn, item, snapshot_id=snapshot_id, metrics=metrics)
        self._update_trace_events(conn, trace["id"], published)
        trace["events_published_json"] = published
        return trace, published

    def _fetch_book(self, token_id: str) -> dict[str, Any]:
        endpoint = f"{(os.getenv('POLYMARKET_CLOB_HOST') or DEFAULT_CLOB_BASE_URL).rstrip('/')}/book"
        started = time.perf_counter()
        try:
            raw, latency_ms = self._clob.get_json(endpoint, params={"token_id": token_id})
        except httpx.HTTPStatusError as exc:
            body = redact_secrets(exc.response.text or "")[:240]
            status = "TOKEN_NOT_FOUND" if exc.response.status_code == 404 else "CLOB_ENDPOINT_ERROR"
            return {"status": status, "latency_ms": int((time.perf_counter() - started) * 1000), "error_summary": body}
        except Exception as exc:
            text = redact_secrets(str(exc))[:240]
            status = "TOKEN_NOT_FOUND" if "token" in text.lower() and "not" in text.lower() else "CLOB_ENDPOINT_ERROR"
            return {"status": status, "latency_ms": int((time.perf_counter() - started) * 1000), "error_summary": text}
        latency = latency_ms if latency_ms is not None else int((time.perf_counter() - started) * 1000)
        if not isinstance(raw, dict) or not raw:
            return {"status": "CLOB_NO_BOOK", "latency_ms": latency}
        bids = raw.get("bids") or raw.get("buy") or []
        asks = raw.get("asks") or raw.get("sell") or []
        if not bids:
            return {"status": "EMPTY_BIDS", "latency_ms": latency, "raw": raw, "asset_id": raw.get("asset_id"), "market": raw.get("market")}
        if not asks:
            return {"status": "EMPTY_ASKS", "latency_ms": latency, "raw": raw, "asset_id": raw.get("asset_id"), "market": raw.get("market")}
        return {"status": "OK", "latency_ms": latency, "raw": raw, "asset_id": raw.get("asset_id"), "market": raw.get("market")}

    def _validate_book(self, clob: dict[str, Any], item: dict[str, Any]) -> str | None:
        raw = clob.get("raw") or {}
        if _clean(raw.get("asset_id") or clob.get("asset_id")) != str(item["token_id"]):
            return "ASSET_ID_MISMATCH"
        if _clean(raw.get("market") or clob.get("market")) != str(item["condition_id"]):
            return "CONDITION_ID_MISMATCH"
        return None

    def _persist_snapshot(self, conn: Any, *, raw: dict[str, Any], item: dict[str, Any], run_id: str) -> tuple[int | None, dict[str, Any]]:
        snapshot = self._snapshotter.normalize_orderbook(
            raw,
            market_id=str(item["market_id"]),
            token_id=str(item["token_id"]),
            side=str(item["side"]),
            source="live_orderbook_watcher",
            correlation_id=run_id,
            raw_payload_ref=f"clob:/book:{item['token_id']}:{datetime.now(UTC).isoformat()}",
            collected_at=datetime.now(UTC),
            freshness_window_seconds=FRESHNESS_SECONDS,
        )
        self._orderbooks.append_snapshot(conn, snapshot)
        row = conn.execute("SELECT * FROM orderbook_snapshots WHERE orderbook_snapshot_id=%s", (snapshot.orderbook_snapshot_id,)).fetchone()
        return (
            int(row["id"]) if row else None,
            {
                "snapshot_ref": snapshot.orderbook_snapshot_id,
                "best_bid": snapshot.best_bid,
                "best_ask": snapshot.best_ask,
                "mid_price": snapshot.mid_price,
                "spread": snapshot.spread,
                "liquidity_score": snapshot.liquidity_score,
                "snapshot_status": snapshot.snapshot_status,
            },
        )

    def _detect_events(self, item: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
        events = [NeuralEventType.ORDERBOOK_REFRESHED.value]
        previous_spread = _float_or_none(item.get("last_spread"))
        new_spread = _float_or_none(metrics.get("spread"))
        if previous_spread is not None and new_spread is not None and _changed(previous_spread, new_spread, abs_threshold=SPREAD_ABS_THRESHOLD, rel_threshold=SPREAD_REL_THRESHOLD):
            events.append(NeuralEventType.SPREAD_CHANGED.value)
        previous_liquidity = _float_or_none(item.get("last_liquidity_score"))
        new_liquidity = _float_or_none(metrics.get("liquidity_score"))
        if previous_liquidity is not None and new_liquidity is not None and _changed(previous_liquidity, new_liquidity, abs_threshold=LIQUIDITY_ABS_THRESHOLD, rel_threshold=LIQUIDITY_REL_THRESHOLD):
            events.append(NeuralEventType.LIQUIDITY_CHANGED.value)
        previous_mid = _mid(item.get("last_best_bid"), item.get("last_best_ask"))
        new_mid = _mid(metrics.get("best_bid"), metrics.get("best_ask"))
        if previous_mid is not None and new_mid is not None and abs(new_mid - previous_mid) >= MID_PRICE_ABS_THRESHOLD:
            events.append(NeuralEventType.MARKET_REPRICING.value)
        return events

    def _publish_events(self, conn: Any, *, trace: dict[str, Any], event_types: list[str]) -> list[str]:
        published: list[str] = []
        for event_type in event_types:
            event = NeuralEvent(
                event_type=event_type,
                correlation_id=trace["run_id"],
                market_id=trace.get("market_id"),
                source_component="Live Token / Orderbook Watcher",
                source_type="CLOB_READ_ONLY",
                priority=4,
                payload_json={
                    "market_id": trace.get("market_id"),
                    "condition_id": trace.get("condition_id"),
                    "token_id": trace.get("token_id"),
                    "side": trace.get("side"),
                    "snapshot_id": trace.get("new_snapshot_id"),
                    "best_bid": trace.get("new_best_bid"),
                    "best_ask": trace.get("new_best_ask"),
                    "spread": trace.get("new_spread"),
                    "liquidity_score": trace.get("new_liquidity_score"),
                    "previous_spread": trace.get("previous_spread"),
                    "spread_delta": trace.get("spread_delta"),
                    "liquidity_delta": trace.get("liquidity_delta"),
                    "reason": trace.get("reason"),
                    "read_only": True,
                },
                source_table="live_orderbook_watcher_traces",
                source_record_id=str(trace["id"]),
                metadata_json={"source_backed": True, "no_trading_authority": True},
            )
            row = self._events.append_event(conn, event)
            self._mesh.resolve_event_with_conn(conn, row)
            published.append(event_type)
        return published

    def _insert_trace(
        self,
        conn: Any,
        *,
        run_id: str,
        item: dict[str, Any],
        clob_status: str,
        reason: str | None,
        metrics: dict[str, Any],
        new_snapshot_id: int | None = None,
        clob: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clob = clob or {}
        spread_delta = _delta(item.get("last_spread"), metrics.get("spread"))
        liquidity_delta = _delta(item.get("last_liquidity_score"), metrics.get("liquidity_score"))
        row = conn.execute(
            """
            INSERT INTO live_orderbook_watcher_traces (
                run_id, watch_id, market_id, condition_id, side, token_id, clob_status,
                previous_snapshot_id, new_snapshot_id, previous_best_bid, new_best_bid,
                previous_best_ask, new_best_ask, previous_spread, new_spread,
                previous_liquidity_score, new_liquidity_score, spread_delta,
                liquidity_delta, reason
            )
            VALUES (
                %(run_id)s, %(watch_id)s, %(market_id)s, %(condition_id)s, %(side)s,
                %(token_id)s, %(clob_status)s, %(previous_snapshot_id)s,
                %(new_snapshot_id)s, %(previous_best_bid)s, %(new_best_bid)s,
                %(previous_best_ask)s, %(new_best_ask)s, %(previous_spread)s,
                %(new_spread)s, %(previous_liquidity_score)s,
                %(new_liquidity_score)s, %(spread_delta)s, %(liquidity_delta)s,
                %(reason)s
            )
            RETURNING *
            """,
            {
                "run_id": run_id,
                "watch_id": item.get("watch_id"),
                "market_id": item.get("market_id"),
                "condition_id": item.get("condition_id"),
                "side": item.get("side"),
                "token_id": item.get("token_id"),
                "clob_status": clob_status,
                "previous_snapshot_id": item.get("last_snapshot_id"),
                "new_snapshot_id": new_snapshot_id,
                "previous_best_bid": item.get("last_best_bid"),
                "new_best_bid": metrics.get("best_bid"),
                "previous_best_ask": item.get("last_best_ask"),
                "new_best_ask": metrics.get("best_ask"),
                "previous_spread": item.get("last_spread"),
                "new_spread": metrics.get("spread"),
                "previous_liquidity_score": item.get("last_liquidity_score"),
                "new_liquidity_score": metrics.get("liquidity_score"),
                "spread_delta": spread_delta,
                "liquidity_delta": liquidity_delta,
                "reason": reason,
            },
        ).fetchone()
        return _json_safe(dict(row))

    def _update_trace_events(self, conn: Any, trace_id: int, events: list[str]) -> None:
        conn.execute("UPDATE live_orderbook_watcher_traces SET events_published_json=%s WHERE id=%s", (Jsonb(events), trace_id))

    def _update_watch_success(self, conn: Any, item: dict[str, Any], *, snapshot_id: int | None, metrics: dict[str, Any]) -> None:
        conn.execute(
            """
            UPDATE live_orderbook_watchlist
            SET status='ACTIVE',
                last_polled_at=now(),
                last_success_at=now(),
                last_snapshot_id=%s,
                last_best_bid=%s,
                last_best_ask=%s,
                last_spread=%s,
                last_liquidity_score=%s,
                failure_count=0,
                updated_at=now()
            WHERE watch_id=%s
            """,
            (snapshot_id, metrics.get("best_bid"), metrics.get("best_ask"), metrics.get("spread"), metrics.get("liquidity_score"), item["watch_id"]),
        )

    def _update_watch_failure(self, conn: Any, item: dict[str, Any], *, status: str, reason: str) -> None:
        failure_count = int(item.get("failure_count") or 0) + 1
        final_status = "DEGRADED" if failure_count >= MAX_FAILURES_BEFORE_DEGRADED and status == "ACTIVE" else status
        conn.execute(
            """
            UPDATE live_orderbook_watchlist
            SET status=%s,
                last_polled_at=now(),
                last_failure_at=now(),
                failure_count=failure_count+1,
                metadata_json=COALESCE(metadata_json,'{}'::jsonb) || %s,
                updated_at=now()
            WHERE watch_id=%s
            """,
            (final_status, Jsonb({"last_failure_reason": reason}), item["watch_id"]),
        )

    def _market_resolved(self, conn: Any, item: dict[str, Any]) -> bool:
        if not _table_exists(conn, "markets_v2"):
            return False
        row = conn.execute("SELECT closed, archived, active, accepting_orders FROM markets_v2 WHERE market_id=%s", (item.get("market_id"),)).fetchone()
        if not row:
            return False
        return bool(row.get("closed")) or bool(row.get("archived")) or row.get("active") is False or row.get("accepting_orders") is False

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "live_orderbook_watcher_runs"):
                return
            conn.execute(
                """
                INSERT INTO live_orderbook_watcher_runs (
                    run_id, cycle_id, started_at, finished_at, system_power, status,
                    dry_run, watch_items_checked, orderbooks_refreshed,
                    spread_changed_count, liquidity_changed_count,
                    token_unavailable_count, market_resolved_count,
                    events_published, snapshots_created, errors_count,
                    blocker_counts_json, safety_counts_before_json,
                    safety_counts_after_json, live_orders_delta, real_orders_delta,
                    metadata_json, error_message
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(started_at)s, %(finished_at)s,
                    %(system_power)s, %(status)s, %(dry_run)s,
                    %(watch_items_checked)s, %(orderbooks_refreshed)s,
                    %(spread_changed_count)s, %(liquidity_changed_count)s,
                    %(token_unavailable_count)s, %(market_resolved_count)s,
                    %(events_published)s, %(snapshots_created)s, %(errors_count)s,
                    %(blocker_counts_json)s, %(safety_counts_before_json)s,
                    %(safety_counts_after_json)s, %(live_orders_delta)s,
                    %(real_orders_delta)s, %(metadata_json)s, %(error_message)s
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                {
                    **payload,
                    "blocker_counts_json": Jsonb(_json_safe(payload.get("blocker_counts") or {})),
                    "safety_counts_before_json": Jsonb(_json_safe(payload.get("safety_counts_before") or {})),
                    "safety_counts_after_json": Jsonb(_json_safe(payload.get("safety_counts_after") or {})),
                    "metadata_json": Jsonb(_json_safe(payload.get("metadata") or {})),
                },
            )

    def _blocked_payload(self, run_id: str, cycle_id: str | None, system_power: str, started_at: datetime, dry_run: bool, reason: str) -> dict[str, Any]:
        safety = self._safety_counts()
        counts = self._counts()
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "system_power": system_power,
            "status": "BLOCKED",
            "dry_run": dry_run,
            "watch_items_checked": 0,
            "orderbooks_refreshed": 0,
            "spread_changed_count": 0,
            "liquidity_changed_count": 0,
            "token_unavailable_count": 0,
            "market_resolved_count": 0,
            "events_published": 0,
            "snapshots_created": 0,
            "errors_count": 0,
            "blocker_counts": {reason: 1},
            "safety_counts_before": safety,
            "safety_counts_after": safety,
            "live_orders_delta": 0,
            "real_orders_delta": 0,
            "metadata": {"reason": reason, "counts": counts, "security_governance_status": SECURITY_GOVERNANCE_STATUS},
            "error_message": reason,
            "before": counts,
            "after": counts,
            "latest_traces": [],
        }

    def _latest_run(self) -> dict[str, Any] | None:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "live_orderbook_watcher_runs"):
                return None
            row = conn.execute("SELECT * FROM live_orderbook_watcher_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _latest_traces(self, *, limit: int) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "live_orderbook_watcher_traces"):
                return []
            rows = conn.execute(
                """
                SELECT *
                FROM live_orderbook_watcher_traces
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _top_watch_items(self, *, limit: int) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            if not _table_exists(conn, "live_orderbook_watchlist"):
                return []
            rows = conn.execute(
                """
                SELECT *
                FROM live_orderbook_watchlist
                ORDER BY priority ASC, updated_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _counts(self) -> dict[str, int]:
        with self._factory.connect() as conn:
            return {
                "watchlist_count": _count_table(conn, "live_orderbook_watchlist"),
                "active_watch_items": _count_where(conn, "live_orderbook_watchlist", "status='ACTIVE'"),
                "degraded_watch_items": _count_where(conn, "live_orderbook_watchlist", "status='DEGRADED'"),
                "token_unavailable_count": _count_where(conn, "live_orderbook_watchlist", "status='TOKEN_UNAVAILABLE'"),
                "watcher_runs": _count_table(conn, "live_orderbook_watcher_runs"),
                "watcher_traces": _count_table(conn, "live_orderbook_watcher_traces"),
                "orderbook_snapshots": _count_table(conn, "orderbook_snapshots"),
                "neural_events": _count_table(conn, "neural_events"),
                "watcher_events": _count_where(conn, "neural_events", "source_component='Live Token / Orderbook Watcher'"),
                "ORDERBOOK_REFRESHED": _count_where(conn, "neural_events", "event_type='ORDERBOOK_REFRESHED' AND source_component='Live Token / Orderbook Watcher'"),
                "SPREAD_CHANGED": _count_where(conn, "neural_events", "event_type='SPREAD_CHANGED' AND source_component='Live Token / Orderbook Watcher'"),
                "LIQUIDITY_CHANGED": _count_where(conn, "neural_events", "event_type='LIQUIDITY_CHANGED' AND source_component='Live Token / Orderbook Watcher'"),
                "TOKEN_BOOK_UNAVAILABLE": _count_where(conn, "neural_events", "event_type='TOKEN_BOOK_UNAVAILABLE' AND source_component='Live Token / Orderbook Watcher'"),
                "MARKET_RESOLVED": _count_where(conn, "neural_events", "event_type='MARKET_RESOLVED' AND source_component='Live Token / Orderbook Watcher'"),
                "mesh_sessions": _count_table(conn, "mesh_sessions"),
                "shared_awareness": _count_table(conn, "mesh_shared_awareness"),
                "brain_opinions": _count_table(conn, "mesh_brain_opinions"),
                "coordinator_decisions": _count_table(conn, "mesh_coordinator_decisions"),
                **self._safety_counts(conn),
            }

    def _safety_counts(self, conn: Any | None = None) -> dict[str, int]:
        if conn is not None:
            return _safety_counts(conn)
        with self._factory.connect() as local:
            return _safety_counts(local)


class _WatcherHttpClient:
    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[Any, int]:
        started = time.perf_counter()
        with httpx.Client(timeout=12.0, headers={"User-Agent": "POLYBOT-live-orderbook-watcher/1.0"}) as client:
            response = client.get(url, params=params)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def _safety_counts(conn: Any) -> dict[str, int]:
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


def _valid_watch_source(row: dict[str, Any]) -> bool:
    return all(_clean(row.get(key)) for key in ("market_id", "condition_id", "side", "token_id", "source_type", "source_id")) and row.get("side") in {"YES", "NO"}


def _watch_id(market_id: str, side: str, token_id: str) -> str:
    return f"live_watch_{market_id}_{side}_{token_id}"


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


def _delta(old: Any, new: Any) -> float | None:
    old_float = _float_or_none(old)
    new_float = _float_or_none(new)
    if old_float is None or new_float is None:
        return None
    return round(new_float - old_float, 6)


def _changed(old: float, new: float, *, abs_threshold: float, rel_threshold: float) -> bool:
    delta = abs(new - old)
    if delta >= abs_threshold:
        return True
    base = abs(old)
    return base > 0 and delta / base >= rel_threshold


def _mid(bid: Any, ask: Any) -> float | None:
    bid_float = _float_or_none(bid)
    ask_float = _float_or_none(ask)
    if bid_float is None or ask_float is None:
        return None
    return round((bid_float + ask_float) / 2, 6)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _error_summary(identifier: Any, exc: Exception) -> str:
    return f"{identifier or 'unknown'}:{type(exc).__name__}:{redact_secrets(str(exc))[:160]}"
