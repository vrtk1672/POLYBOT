from __future__ import annotations

from datetime import UTC, datetime
import os
import time
from typing import Any
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository
from app.services.source_status import DEFAULT_CLOB_BASE_URL


DEFAULT_ORDERBOOK_TTL_SECONDS = 180
DEFAULT_RATE_LIMIT_SECONDS = 60
VALID_SNAPSHOT_STATES = {"OK", "PARTIAL"}


class LastMileOrderbookRefreshService:
    """Targeted pre-intent orderbook refresh for PAPER runtime decisions.

    This service is deliberately narrow: it refreshes only the exact
    market/token/side needed by a candidate that is otherwise close to PAPER
    entry. It never creates intents, orders, fills, positions, or live actions.
    """

    def __init__(self, *, http_client: Any | None = None) -> None:
        self._http = http_client or _LastMileOrderbookHttpClient()
        self._snapshotter = OrderbookSnapshotter()
        self._orderbooks = OrderbookSnapshotRepository()

    def ensure_fresh(
        self,
        conn: Any,
        *,
        decision_id: str,
        source_review_id: str | None,
        market_id: str | None,
        condition_id: str | None,
        token_id: str | None,
        side: str | None,
        ttl_seconds: int = DEFAULT_ORDERBOOK_TTL_SECONDS,
        rate_limit_seconds: int = DEFAULT_RATE_LIMIT_SECONDS,
        force: bool = False,
    ) -> dict[str, Any]:
        ensure_tables(conn)
        started_at = datetime.now(UTC)
        attempt_id = f"last_mile_orderbook_{uuid4().hex}"
        side_norm = str(side or "").upper()
        ttl_seconds = max(1, int(ttl_seconds or DEFAULT_ORDERBOOK_TTL_SECONDS))
        rate_limit_seconds = max(1, int(rate_limit_seconds or DEFAULT_RATE_LIMIT_SECONDS))

        pre = latest_matching_orderbook(conn, market_id=market_id, token_id=token_id, side=side_norm)
        pre_age = orderbook_age_seconds(pre)
        if is_fresh_orderbook(pre, ttl_seconds=ttl_seconds):
            payload = {
                "attempt_id": attempt_id,
                "decision_id": decision_id,
                "source_review_id": source_review_id,
                "market_id": market_id,
                "condition_id": condition_id,
                "token_id": token_id,
                "side": side_norm,
                "refresh_state": "FRESH_ALREADY_AVAILABLE",
                "refresh_error": None,
                "pre_refresh_snapshot_id": pre.get("id") if pre else None,
                "pre_refresh_age_seconds": pre_age,
                "post_refresh_snapshot_id": pre.get("id") if pre else None,
                "post_refresh_age_seconds": pre_age,
                "orderbook_ttl_seconds": ttl_seconds,
                "stale_cleared": True,
                "started_at": started_at,
                "completed_at": datetime.now(UTC),
                "metadata_json": {"selected_without_connector": True},
            }
            _record_attempt(conn, payload)
            return _json_safe({**payload, "orderbook": pre})

        validation_error = _input_validation_error(market_id=market_id, token_id=token_id, side=side_norm)
        if validation_error:
            payload = _base_payload(
                attempt_id=attempt_id,
                decision_id=decision_id,
                source_review_id=source_review_id,
                market_id=market_id,
                condition_id=condition_id,
                token_id=token_id,
                side=side_norm,
                ttl_seconds=ttl_seconds,
                pre=pre,
                started_at=started_at,
                refresh_state="BLOCKED",
                refresh_error=validation_error,
                metadata={"reason": validation_error},
            )
            _record_attempt(conn, payload)
            return _json_safe({**payload, "orderbook": pre})

        if not force:
            recent = _recent_attempt(
                conn,
                market_id=str(market_id),
                token_id=str(token_id),
                side=side_norm,
                rate_limit_seconds=rate_limit_seconds,
            )
            if recent:
                payload = _base_payload(
                    attempt_id=attempt_id,
                    decision_id=decision_id,
                    source_review_id=source_review_id,
                    market_id=market_id,
                    condition_id=condition_id,
                    token_id=token_id,
                    side=side_norm,
                    ttl_seconds=ttl_seconds,
                    pre=pre,
                    started_at=started_at,
                    refresh_state="RATE_LIMITED_RECENT_ATTEMPT",
                    refresh_error=str(recent.get("refresh_error") or recent.get("refresh_state") or "RECENT_ATTEMPT"),
                    metadata={"recent_attempt_id": recent.get("attempt_id")},
                )
                _record_attempt(conn, payload)
                return _json_safe({**payload, "orderbook": pre, "recent_attempt": recent})

        endpoint = f"{(os.getenv('POLYMARKET_CLOB_HOST') or DEFAULT_CLOB_BASE_URL).rstrip('/')}/book"
        latency_ms: int | None = None
        raw: Any = None
        try:
            started = time.perf_counter()
            raw, latency_ms = self._http.get_json(endpoint, params={"token_id": token_id})
            if latency_ms is None:
                latency_ms = int((time.perf_counter() - started) * 1000)
        except Exception as exc:
            payload = _base_payload(
                attempt_id=attempt_id,
                decision_id=decision_id,
                source_review_id=source_review_id,
                market_id=market_id,
                condition_id=condition_id,
                token_id=token_id,
                side=side_norm,
                ttl_seconds=ttl_seconds,
                pre=pre,
                started_at=started_at,
                refresh_state="FAILED",
                refresh_error="ORDERBOOK_CONNECTOR_ERROR",
                connector_latency_ms=latency_ms,
                metadata={"error_type": type(exc).__name__, "error_summary": str(exc)[:180]},
            )
            _record_attempt(conn, payload)
            return _json_safe({**payload, "orderbook": pre})

        raw_error = _raw_orderbook_error(raw, token_id=str(token_id), condition_id=condition_id)
        if raw_error:
            payload = _base_payload(
                attempt_id=attempt_id,
                decision_id=decision_id,
                source_review_id=source_review_id,
                market_id=market_id,
                condition_id=condition_id,
                token_id=token_id,
                side=side_norm,
                ttl_seconds=ttl_seconds,
                pre=pre,
                started_at=started_at,
                refresh_state="FAILED",
                refresh_error=raw_error,
                connector_latency_ms=latency_ms,
                metadata={"raw_type": type(raw).__name__},
            )
            _record_attempt(conn, payload)
            return _json_safe({**payload, "orderbook": pre})

        collected_at = datetime.now(UTC)
        snapshot = self._snapshotter.normalize_orderbook(
            raw,
            market_id=str(market_id),
            token_id=str(token_id),
            side=side_norm,
            source="polymarket_clob_last_mile_paper",
            correlation_id=attempt_id,
            raw_payload_ref=f"clob:/book:{token_id}:{collected_at.isoformat()}",
            collected_at=collected_at,
            freshness_window_seconds=ttl_seconds,
            metadata_json={
                "decision_id": decision_id,
                "source_review_id": source_review_id,
                "refresh_reason": "paper_runtime_last_mile_orderbook",
                "refresh_scope": "PAPER_PRE_INTENT",
                "source_service": "LastMileOrderbookRefreshService",
                "market_id": market_id,
                "condition_id": condition_id,
                "side": side_norm,
                "token_id": token_id,
                "non_trading_evidence_only": True,
            },
        )
        if snapshot.snapshot_status not in VALID_SNAPSHOT_STATES:
            payload = _base_payload(
                attempt_id=attempt_id,
                decision_id=decision_id,
                source_review_id=source_review_id,
                market_id=market_id,
                condition_id=condition_id,
                token_id=token_id,
                side=side_norm,
                ttl_seconds=ttl_seconds,
                pre=pre,
                started_at=started_at,
                refresh_state="FAILED",
                refresh_error="ORDERBOOK_EMPTY" if snapshot.snapshot_status == "EMPTY" else "ORDERBOOK_REFRESH_FAILED",
                connector_latency_ms=latency_ms,
                metadata={"snapshot_status": snapshot.snapshot_status, "stale_reason": snapshot.stale_reason},
            )
            _record_attempt(conn, payload)
            return _json_safe({**payload, "orderbook": pre})

        self._orderbooks.append_snapshot(conn, snapshot)
        post = latest_matching_orderbook(conn, market_id=market_id, token_id=token_id, side=side_norm)
        post_age = orderbook_age_seconds(post)
        stale_cleared = is_fresh_orderbook(post, ttl_seconds=ttl_seconds)
        payload = {
            "attempt_id": attempt_id,
            "decision_id": decision_id,
            "source_review_id": source_review_id,
            "market_id": market_id,
            "condition_id": condition_id,
            "token_id": token_id,
            "side": side_norm,
            "refresh_state": "REFRESHED_FRESH" if stale_cleared else "FAILED",
            "refresh_error": None if stale_cleared else "ORDERBOOK_TTL_EXPIRED_AFTER_REFRESH",
            "pre_refresh_snapshot_id": pre.get("id") if pre else None,
            "pre_refresh_age_seconds": pre_age,
            "post_refresh_snapshot_id": post.get("id") if post else None,
            "post_refresh_age_seconds": post_age,
            "orderbook_ttl_seconds": ttl_seconds,
            "stale_cleared": stale_cleared,
            "connector_latency_ms": latency_ms,
            "started_at": started_at,
            "completed_at": datetime.now(UTC),
            "metadata_json": {
                "snapshot_ref": snapshot.orderbook_snapshot_id,
                "snapshot_status": snapshot.snapshot_status,
                "best_bid": snapshot.best_bid,
                "best_ask": snapshot.best_ask,
                "spread": snapshot.spread,
                "liquidity_score": snapshot.liquidity_score,
            },
        }
        _record_attempt(conn, payload)
        return _json_safe({**payload, "orderbook": post})


def ensure_tables(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS last_mile_orderbook_refresh_attempts (
            id BIGSERIAL PRIMARY KEY,
            attempt_id TEXT NOT NULL UNIQUE,
            decision_id TEXT,
            source_review_id TEXT,
            market_id TEXT,
            condition_id TEXT,
            token_id TEXT,
            side TEXT,
            refresh_state TEXT NOT NULL,
            refresh_error TEXT,
            pre_refresh_snapshot_id BIGINT,
            pre_refresh_age_seconds NUMERIC,
            post_refresh_snapshot_id BIGINT,
            post_refresh_age_seconds NUMERIC,
            orderbook_ttl_seconds INTEGER NOT NULL DEFAULT 180,
            stale_cleared BOOLEAN NOT NULL DEFAULT FALSE,
            connector_latency_ms INTEGER,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_last_mile_orderbook_market_token_side
            ON last_mile_orderbook_refresh_attempts (market_id, token_id, side, started_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_last_mile_orderbook_decision
            ON last_mile_orderbook_refresh_attempts (decision_id, started_at DESC)
        """
    )


def latest_matching_orderbook(
    conn: Any,
    *,
    market_id: str | None,
    token_id: str | None,
    side: str | None,
) -> dict[str, Any] | None:
    if not market_id or not _table_exists(conn, "orderbook_snapshots"):
        return None
    side_norm = str(side or "").upper()
    if token_id:
        row = conn.execute(
            """
            SELECT *,
                   EXTRACT(EPOCH FROM (now() - COALESCE(snapshot_at, collected_at, created_at))) AS age_seconds
            FROM orderbook_snapshots
            WHERE market_id=%s
              AND token_id=%s
              AND (%s::text = '' OR side=%s OR side IS NULL)
              AND COALESCE(is_stale, false) IS FALSE
              AND snapshot_status IN ('OK','PARTIAL')
            ORDER BY
              CASE WHEN side=%s THEN 0 ELSE 1 END,
              COALESCE(snapshot_at, collected_at, created_at) DESC,
              id DESC
            LIMIT 1
            """,
            (market_id, token_id, side_norm, side_norm, side_norm),
        ).fetchone()
        return dict(row) if row else None
    if side_norm in {"YES", "NO"}:
        row = conn.execute(
            """
            SELECT *,
                   EXTRACT(EPOCH FROM (now() - COALESCE(snapshot_at, collected_at, created_at))) AS age_seconds
            FROM orderbook_snapshots
            WHERE market_id=%s
              AND side=%s
              AND COALESCE(is_stale, false) IS FALSE
              AND snapshot_status IN ('OK','PARTIAL')
            ORDER BY COALESCE(snapshot_at, collected_at, created_at) DESC, id DESC
            LIMIT 1
            """,
            (market_id, side_norm),
        ).fetchone()
        return dict(row) if row else None
    return None


def is_fresh_orderbook(row: dict[str, Any] | None, *, ttl_seconds: int = DEFAULT_ORDERBOOK_TTL_SECONDS) -> bool:
    if not row:
        return False
    if str(row.get("snapshot_status") or "").upper() not in VALID_SNAPSHOT_STATES:
        return False
    if bool(row.get("is_stale")):
        return False
    return orderbook_age_seconds(row) <= ttl_seconds


def orderbook_age_seconds(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    if row.get("age_seconds") is not None:
        try:
            return max(0.0, float(row.get("age_seconds")))
        except (TypeError, ValueError):
            pass
    ts = row.get("snapshot_at") or row.get("collected_at") or row.get("created_at")
    if ts is None:
        return None
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(ts, datetime):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - ts.astimezone(UTC)).total_seconds())


class _LastMileOrderbookHttpClient:
    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> tuple[Any, int]:
        started = time.perf_counter()
        with httpx.Client(timeout=self._timeout_seconds, follow_redirects=True, headers={"User-Agent": "POLYBOT-last-mile-orderbook/1.0"}) as client:
            response = client.get(url, params=params)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms


def _record_attempt(conn: Any, payload: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO last_mile_orderbook_refresh_attempts (
            attempt_id, decision_id, source_review_id, market_id, condition_id,
            token_id, side, refresh_state, refresh_error,
            pre_refresh_snapshot_id, pre_refresh_age_seconds,
            post_refresh_snapshot_id, post_refresh_age_seconds,
            orderbook_ttl_seconds, stale_cleared, connector_latency_ms,
            metadata_json, started_at, completed_at
        )
        VALUES (
            %(attempt_id)s, %(decision_id)s, %(source_review_id)s, %(market_id)s,
            %(condition_id)s, %(token_id)s, %(side)s, %(refresh_state)s,
            %(refresh_error)s, %(pre_refresh_snapshot_id)s,
            %(pre_refresh_age_seconds)s, %(post_refresh_snapshot_id)s,
            %(post_refresh_age_seconds)s, %(orderbook_ttl_seconds)s,
            %(stale_cleared)s, %(connector_latency_ms)s,
            %(metadata_json)s, %(started_at)s, %(completed_at)s
        )
        ON CONFLICT (attempt_id) DO UPDATE SET
            refresh_state=EXCLUDED.refresh_state,
            refresh_error=EXCLUDED.refresh_error,
            post_refresh_snapshot_id=EXCLUDED.post_refresh_snapshot_id,
            post_refresh_age_seconds=EXCLUDED.post_refresh_age_seconds,
            stale_cleared=EXCLUDED.stale_cleared,
            metadata_json=EXCLUDED.metadata_json,
            completed_at=EXCLUDED.completed_at,
            updated_at=now()
        """,
        {**payload, "metadata_json": Jsonb(_json_safe(payload.get("metadata_json") or {}))},
    )


def _recent_attempt(conn: Any, *, market_id: str, token_id: str, side: str, rate_limit_seconds: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM last_mile_orderbook_refresh_attempts
        WHERE market_id=%s
          AND token_id=%s
          AND side=%s
          AND started_at >= now() - (%s::text || ' seconds')::interval
        ORDER BY started_at DESC, id DESC
        LIMIT 1
        """,
        (market_id, token_id, side, rate_limit_seconds),
    ).fetchone()
    return dict(row) if row else None


def _base_payload(
    *,
    attempt_id: str,
    decision_id: str,
    source_review_id: str | None,
    market_id: str | None,
    condition_id: str | None,
    token_id: str | None,
    side: str,
    ttl_seconds: int,
    pre: dict[str, Any] | None,
    started_at: datetime,
    refresh_state: str,
    refresh_error: str | None,
    connector_latency_ms: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "attempt_id": attempt_id,
        "decision_id": decision_id,
        "source_review_id": source_review_id,
        "market_id": market_id,
        "condition_id": condition_id,
        "token_id": token_id,
        "side": side,
        "refresh_state": refresh_state,
        "refresh_error": refresh_error,
        "pre_refresh_snapshot_id": pre.get("id") if pre else None,
        "pre_refresh_age_seconds": orderbook_age_seconds(pre),
        "post_refresh_snapshot_id": pre.get("id") if pre else None,
        "post_refresh_age_seconds": orderbook_age_seconds(pre),
        "orderbook_ttl_seconds": ttl_seconds,
        "stale_cleared": False,
        "connector_latency_ms": connector_latency_ms,
        "started_at": started_at,
        "completed_at": datetime.now(UTC),
        "metadata_json": metadata or {},
    }


def _input_validation_error(*, market_id: str | None, token_id: str | None, side: str) -> str | None:
    if not market_id:
        return "ORDERBOOK_MARKET_MISMATCH"
    if not token_id:
        return "ORDERBOOK_TOKEN_MISMATCH"
    if side not in {"YES", "NO"}:
        return "ORDERBOOK_TOKEN_MISMATCH"
    return None


def _raw_orderbook_error(raw: Any, *, token_id: str, condition_id: str | None) -> str | None:
    if not isinstance(raw, dict) or not raw:
        return "ORDERBOOK_EMPTY"
    raw_token = str(raw.get("asset_id") or raw.get("token_id") or "")
    if raw_token and raw_token != str(token_id):
        return "ORDERBOOK_TOKEN_MISMATCH"
    raw_market = str(raw.get("market") or raw.get("condition_id") or "")
    if condition_id and raw_market and raw_market.lower() != str(condition_id).lower():
        return "ORDERBOOK_MARKET_MISMATCH"
    bids = raw.get("bids") or raw.get("buy") or []
    asks = raw.get("asks") or raw.get("sell") or []
    if not bids or not asks:
        return "ORDERBOOK_EMPTY"
    return None


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value
