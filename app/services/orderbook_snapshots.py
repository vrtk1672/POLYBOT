from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.repositories.market_registry_repository import MarketRegistryRepository
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository


OrderbookFetcher = Callable[[str], dict[str, Any]]


class OrderbookSnapshotService:
    freshness_window_seconds = 120

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        fetcher: OrderbookFetcher | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._markets = MarketRegistryRepository()
        self._repository = OrderbookSnapshotRepository()
        self._snapshotter = OrderbookSnapshotter(connection_factory=self._factory)
        self._fetcher = fetcher or _fetch_polymarket_clob_book

    def collect_snapshots(
        self,
        *,
        limit: int = 50,
        market_ids: list[str] | None = None,
        source: str = "auto",
    ) -> dict[str, Any]:
        run_id = f"orderbook_run_{uuid4().hex}"
        started_at = datetime.now(UTC)
        safety_before = self._safety_counts()
        candidates = self._candidate_markets(limit=limit, market_ids=market_ids or [])
        source_name = "polymarket_clob" if source in {"auto", "", None} else source

        created = 0
        updated = 0
        ok = 0
        partial = 0
        empty = 0
        stale = 0
        errors: list[str] = []

        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                for market in candidates:
                    for token in _market_tokens(market):
                        try:
                            raw = self._fetcher(token["token_id"])
                            collected_at = datetime.now(UTC)
                            snapshot = self._snapshotter.normalize_orderbook(
                                raw,
                                market_id=str(market["market_id"]),
                                token_id=token["token_id"],
                                side=token["side"],
                                source=source_name,
                                correlation_id=run_id,
                                raw_payload_ref=f"{source_name}:book:{token['token_id']}:{collected_at.isoformat()}",
                                collected_at=collected_at,
                                freshness_window_seconds=self.freshness_window_seconds,
                            )
                            self._repository.append_snapshot(conn, snapshot)
                            created += 1
                            if snapshot.snapshot_status == "OK":
                                ok += 1
                            elif snapshot.snapshot_status == "PARTIAL":
                                partial += 1
                            elif snapshot.snapshot_status == "EMPTY":
                                empty += 1
                            if snapshot.is_stale:
                                stale += 1
                        except Exception as exc:
                            errors.append(f"{market['market_id']}:{token['token_id']}:{type(exc).__name__}:{exc}")
                status = "OK" if created > 0 and not errors else "PARTIAL" if created > 0 else "ERROR"
                self._insert_run(
                    conn,
                    run_id=run_id,
                    status=status,
                    markets_checked=len(candidates),
                    snapshots_created=created,
                    snapshots_updated=updated,
                    ok_snapshots=ok,
                    partial_orderbooks=partial,
                    empty_orderbooks=empty,
                    stale_count=stale,
                    error_count=len(errors),
                    started_at=started_at,
                    error_summary="; ".join(errors[:10]) or None,
                )
        safety_after = self._safety_counts()
        deltas = {key: max(0, safety_after.get(key, 0) - safety_before.get(key, 0)) for key in safety_after}
        return {
            "mock_data": False,
            "run_id": run_id,
            "status": "OK" if created > 0 and not errors else "PARTIAL" if created > 0 else "ERROR",
            "markets_checked": len(candidates),
            "snapshots_created": created,
            "snapshots_updated": updated,
            "ok_snapshots": ok,
            "partial_snapshots": partial,
            "empty_orderbooks": empty,
            "stale_snapshots": stale,
            "error_count": len(errors),
            "paper_ready_before": False,
            "paper_ready_after": False,
            "orders_created": deltas.get("orders", 0),
            "order_intents_created": deltas.get("order_intents", 0),
            "fills_created": deltas.get("fills", 0),
            "positions_created": deltas.get("positions", 0),
            "live_actions_created": deltas.get("live_actions", 0),
            "errors": errors[:10],
        }

    def list_recent(
        self,
        *,
        limit: int = 50,
        market_id: str | None = None,
        source: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "count": 0, "items": []}
        with self._factory.connect() as conn:
            rows = self._repository.list_recent(conn, limit=limit, market_id=market_id, source=source, status=status)
        return {"mock_data": False, "count": len(rows), "items": [_serialize(row) for row in rows]}

    def get_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary("DISABLED")
        with self._factory.connect() as conn:
            if not _table_exists(conn, "orderbook_snapshots"):
                return _empty_summary("MISSING")
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_snapshots,
                    COUNT(*) FILTER (
                        WHERE is_stale = false
                          AND snapshot_status IN ('OK', 'PARTIAL')
                          AND collected_at >= now() - (%s || ' seconds')::interval
                    ) AS fresh_snapshots,
                    COUNT(*) FILTER (WHERE is_stale = true OR collected_at < now() - (%s || ' seconds')::interval) AS stale_snapshots,
                    COUNT(*) FILTER (WHERE snapshot_status = 'OK') AS ok_snapshots,
                    COUNT(*) FILTER (WHERE snapshot_status = 'PARTIAL') AS partial_snapshots,
                    COUNT(*) FILTER (WHERE snapshot_status = 'EMPTY') AS empty_orderbooks,
                    COUNT(*) FILTER (WHERE snapshot_status = 'ERROR') AS error_count,
                    COUNT(DISTINCT market_id) AS markets_with_orderbook,
                    MAX(collected_at) AS latest_collected_at,
                    AVG(spread) FILTER (WHERE spread IS NOT NULL) AS avg_spread,
                    AVG(liquidity_score) FILTER (WHERE liquidity_score IS NOT NULL) AS avg_liquidity_score
                FROM orderbook_snapshots
                """,
                (self.freshness_window_seconds, self.freshness_window_seconds),
            ).fetchone()
            active_markets = conn.execute(
                "SELECT COUNT(*) AS count FROM markets_v2 WHERE active = true AND closed = false AND accepting_orders = true"
            ).fetchone()["count"]
            latest = conn.execute(
                """
                SELECT *
                FROM orderbook_snapshots
                ORDER BY collected_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            stale_rows = conn.execute(
                """
                SELECT market_id, token_id, snapshot_status, stale_reason, collected_at
                FROM orderbook_snapshots
                WHERE is_stale = true OR collected_at < now() - (%s || ' seconds')::interval
                ORDER BY collected_at DESC, id DESC
                LIMIT 10
                """,
                (self.freshness_window_seconds,),
            ).fetchall()
            latest_run = conn.execute("SELECT * FROM orderbook_snapshot_runs ORDER BY started_at DESC, id DESC LIMIT 1").fetchone() if _table_exists(conn, "orderbook_snapshot_runs") else None

        total = int(row["total_snapshots"] or 0)
        fresh = int(row["fresh_snapshots"] or 0)
        markets_with_orderbook = int(row["markets_with_orderbook"] or 0)
        coverage = round(markets_with_orderbook / int(active_markets or 1), 6) if active_markets else 0.0
        status = "OK" if fresh > 0 else "DEGRADED" if total > 0 else "EMPTY"
        return {
            "mock_data": False,
            "status": status,
            "total_snapshots": total,
            "fresh_snapshots": fresh,
            "stale_snapshots": int(row["stale_snapshots"] or 0),
            "ok_snapshots": int(row["ok_snapshots"] or 0),
            "partial_snapshots": int(row["partial_snapshots"] or 0),
            "empty_orderbooks": int(row["empty_orderbooks"] or 0),
            "error_count": int(row["error_count"] or 0),
            "markets_with_orderbook": markets_with_orderbook,
            "active_tradable_markets": int(active_markets or 0),
            "latest_collected_at": _iso(row["latest_collected_at"]),
            "freshness_window_seconds": self.freshness_window_seconds,
            "orderbook_coverage_ratio": coverage,
            "avg_spread": _float(row["avg_spread"]),
            "avg_liquidity_score": _float(row["avg_liquidity_score"]),
            "top_stale_markets": [_serialize(item) for item in stale_rows],
            "latest_snapshots": [_serialize(item) for item in latest],
            "last_run": _serialize(latest_run),
            "paper_ready": False,
            "analysis_status": "OK",
        }

    def _candidate_markets(self, *, limit: int, market_ids: list[str]) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if market_ids:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM markets_v2
                    WHERE market_id = ANY(%s)
                      AND active = true
                      AND closed = false
                      AND accepting_orders = true
                    ORDER BY last_seen_at DESC, id DESC
                    LIMIT %s
                    """,
                    (market_ids, limit),
                ).fetchall()
            else:
                rows = self._markets.list_markets(conn, active=True, closed=False, limit=limit)
                rows = [row for row in rows if row.get("accepting_orders") is True]
        return [dict(row) for row in rows if _market_tokens(row)]

    def _insert_run(self, conn, **values: Any) -> None:
        conn.execute(
            """
            INSERT INTO orderbook_snapshot_runs (
                run_id, status, markets_checked, snapshots_created, snapshots_updated,
                ok_snapshots, partial_orderbooks, empty_orderbooks, stale_count, error_count,
                paper_ready_before, paper_ready_after, orders_created, order_intents_created,
                fills_created, positions_created, live_actions_created, started_at, finished_at, error_summary
            )
            VALUES (
                %(run_id)s, %(status)s, %(markets_checked)s, %(snapshots_created)s, %(snapshots_updated)s,
                %(ok_snapshots)s, %(partial_orderbooks)s, %(empty_orderbooks)s, %(stale_count)s, %(error_count)s,
                false, false, 0, 0, 0, 0, 0, %(started_at)s, now(), %(error_summary)s
            )
            """,
            values,
        )

    def _safety_counts(self) -> dict[str, int]:
        return {
            "orders": self._count_table("paper_orders") + self._count_table("shadow_orders") + self._count_table("live_orders"),
            "order_intents": self._count_table("order_intents"),
            "fills": self._count_table("paper_fills") + self._count_table("fills_v2"),
            "positions": self._count_table("paper_positions") + self._count_table("positions"),
            "live_actions": self._count_table("live_orders"),
        }

    def _count_table(self, table: str) -> int:
        if not self._factory.enabled:
            return 0
        try:
            with self._factory.connect() as conn:
                if not _table_exists(conn, table):
                    return 0
                return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
        except Exception:
            return 0


def _fetch_polymarket_clob_book(token_id: str) -> dict[str, Any]:
    url = "https://clob.polymarket.com/book?" + urllib.parse.urlencode({"token_id": token_id})
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "POLYBOT-orderbook-snapshot/4C-M"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _market_tokens(market: dict[str, Any]) -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    yes = market.get("yes_token_id")
    no = market.get("no_token_id")
    if yes:
        tokens.append({"token_id": str(yes), "side": "YES"})
    if no:
        tokens.append({"token_id": str(no), "side": "NO"})
    return tokens


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    output: dict[str, Any] = {}
    for key, value in dict(row).items():
        if hasattr(value, "isoformat"):
            output[key] = value.isoformat()
        else:
            output[key] = float(value) if value.__class__.__name__ == "Decimal" else value
    return output


def _empty_summary(status: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "total_snapshots": 0,
        "fresh_snapshots": 0,
        "stale_snapshots": 0,
        "ok_snapshots": 0,
        "partial_snapshots": 0,
        "empty_orderbooks": 0,
        "error_count": 0,
        "markets_with_orderbook": 0,
        "latest_collected_at": None,
        "freshness_window_seconds": OrderbookSnapshotService.freshness_window_seconds,
        "orderbook_coverage_ratio": 0.0,
        "avg_spread": 0.0,
        "avg_liquidity_score": 0.0,
        "top_stale_markets": [],
        "last_run": None,
        "paper_ready": False,
        "analysis_status": "OK",
    }


def _float(value: Any) -> float:
    try:
        return round(float(value or 0), 6)
    except (TypeError, ValueError):
        return 0.0


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _table_exists(conn, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()["reg"] is not None
