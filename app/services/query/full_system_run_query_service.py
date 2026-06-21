from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory


COUNT_TABLES = (
    "live_orders",
    "paper_orders",
    "orders_v2",
    "fills_v2",
    "exit_plans",
    "exit_intents",
    "no_trade_log",
    "trade_reviews",
    "model_adjustments",
    "event_log",
)

PIPELINE_TABLES = {
    "markets": ("markets",),
    "news": ("news_events", "news_neuron_signals"),
    "social": ("social_signals", "social_neuron_signals"),
    "whales": ("whale_events", "whale_signals"),
    "technical": ("market_technical_snapshots", "technical_truth_v2"),
    "memory": ("market_memory_v2", "market_memory_snapshots"),
    "brains": ("context_brain_outputs", "capital_brain_outputs"),
    "opportunities": ("opportunity_scores_v2",),
    "strategy": ("strategy_routes_v2", "engine_decisions"),
    "capital": ("capital_allocations_v2", "capital_state_v2"),
    "risk": ("risk_gate_decisions", "risk_governor_state"),
    "execution": ("orders_v2", "fills_v2"),
    "exits": ("exit_plans", "exit_intents", "exit_failures"),
    "no_trade": ("no_trade_log", "no_trade_reasons"),
    "learning": ("trade_reviews", "engine_learning", "no_trade_learning"),
}

DASHBOARD_ENDPOINTS = (
    "/dashboard/api/v2/overview",
    "/dashboard/api/v2/events",
    "/dashboard/api/v2/risk",
    "/dashboard/api/v2/capital",
    "/dashboard/api/v2/execution",
    "/dashboard/api/v2/exits",
    "/dashboard/api/v2/no-trade",
    "/dashboard/api/v2/learning",
)

HEALTH_ENDPOINTS = (
    "/healthz",
    "/runtime/state",
    "/runtime/health",
    "/events/lag",
    "/data/coverage",
    "/learning/health",
    "/no-trade/health",
    "/exits/health",
    "/execution/health",
    "/risk/health",
)


def json_default(value: Any) -> str | float:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def evaluate_no_live_mutation(before: dict[str, int], after: dict[str, int], mode: str) -> dict[str, Any]:
    mode = mode.upper()
    deltas = {table: safe_int(after.get(table)) - safe_int(before.get(table)) for table in COUNT_TABLES}
    violations: list[str] = []

    if deltas.get("live_orders", 0) != 0:
        violations.append("live_orders_changed")

    if mode == "DATA_ONLY":
        for table in ("paper_orders", "orders_v2", "fills_v2", "exit_intents"):
            if deltas.get(table, 0) > 0:
                violations.append(f"{table}_created_in_data_only")

    if mode == "PAPER":
        for table in ("orders_v2", "fills_v2", "exit_intents"):
            if deltas.get(table, 0) < 0:
                violations.append(f"{table}_unexpected_decrease")

    return {
        "mode": mode,
        "ok": not violations,
        "violations": violations,
        "deltas": deltas,
        "rule": "DATA_ONLY forbids paper/live execution records; PAPER permits internal paper/shadow only.",
    }


def evaluate_dashboard_payloads(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    checked: list[dict[str, Any]] = []
    violations: list[str] = []
    stale_count = 0
    insufficient_count = 0

    for endpoint, payload in payloads.items():
        status = payload.get("status", "UNKNOWN")
        data_source = payload.get("data_source")
        stale = bool(payload.get("stale"))
        errors = payload.get("errors") or []
        if stale:
            stale_count += 1
        if status in {"NO_DATA", "INSUFFICIENT_DATA", "DEGRADED"}:
            insufficient_count += 1
        if isinstance(data_source, dict) and data_source.get("mock_data") is True:
            violations.append(f"{endpoint}:mock_data_true")
        if isinstance(errors, list):
            for error in errors:
                if isinstance(error, dict) and error.get("mock_data") is True:
                    violations.append(f"{endpoint}:mock_error_data")
        checked.append(
            {
                "endpoint": endpoint,
                "status": status,
                "stale": stale,
                "data_confidence": payload.get("data_confidence"),
                "error_count": len(errors) if isinstance(errors, list) else 1,
            }
        )

    return {
        "ok": not violations,
        "violations": violations,
        "checked": checked,
        "stale_count": stale_count,
        "insufficient_or_degraded_count": insufficient_count,
    }


def detect_duplicate_active_orders(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], list[str]] = {}
    for row in rows:
        key = (
            str(row.get("market_id") or ""),
            str(row.get("side") or ""),
            str(row.get("engine") or ""),
        )
        buckets.setdefault(key, []).append(str(row.get("order_id") or row.get("id") or "unknown"))
    duplicates: list[dict[str, Any]] = []
    for (market_id, side, engine), order_ids in buckets.items():
        if len(order_ids) > 1:
            duplicates.append(
                {
                    "market_id": market_id,
                    "side": side,
                    "engine": engine,
                    "count": len(order_ids),
                    "order_ids": order_ids,
                }
            )
    return duplicates


@dataclass(slots=True)
class HttpResult:
    endpoint: str
    ok: bool
    status_code: int | None
    payload: dict[str, Any] | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "ok": self.ok,
            "status_code": self.status_code,
            "payload": self.payload,
            "error": self.error,
        }


class FullSystemRunQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def fetch_count_snapshot(self) -> dict[str, int]:
        if not self.enabled:
            return {table: 0 for table in COUNT_TABLES}
        with self._factory.connect() as conn:
            return {table: self._table_count(conn, table) for table in COUNT_TABLES}

    def fetch_pipeline_counts(self) -> dict[str, dict[str, Any]]:
        if not self.enabled:
            return {
                name: {"status": "INSUFFICIENT_DATA", "tables": {}, "total_rows": 0}
                for name in PIPELINE_TABLES
            }
        with self._factory.connect() as conn:
            result: dict[str, dict[str, Any]] = {}
            for name, tables in PIPELINE_TABLES.items():
                table_counts = {table: self._table_count(conn, table) for table in tables}
                existing_counts = {table: count for table, count in table_counts.items() if count >= 0}
                total = sum(existing_counts.values())
                status = "OK" if total > 0 else "NO_DATA"
                if not existing_counts:
                    status = "INSUFFICIENT_DATA"
                result[name] = {"status": status, "tables": table_counts, "total_rows": total}
            return result

    def fetch_event_lag(self) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "INSUFFICIENT_DATA", "reason": "database_disabled"}
        with self._factory.connect() as conn:
            if not self._table_exists(conn, "event_log"):
                return {"status": "INSUFFICIENT_DATA", "reason": "event_log_missing"}
            row = conn.execute(
                """
                SELECT COUNT(*) AS total_events, MAX(stored_at) AS latest_event_ts
                FROM event_log
                """
            ).fetchone()
            latest = row["latest_event_ts"] if row else None
            lag_seconds = None
            if latest is not None:
                lag = conn.execute("SELECT EXTRACT(EPOCH FROM (now() - %s)) AS lag", (latest,)).fetchone()
                lag_seconds = float(lag["lag"] or 0)
            dlq = {"dlq_count": 0, "open_dlq_count": 0}
            if self._table_exists(conn, "event_dlq"):
                dlq_row = conn.execute(
                    "SELECT COUNT(*) AS count, COUNT(*) FILTER (WHERE status = 'OPEN') AS open_count FROM event_dlq"
                ).fetchone()
                dlq = {
                    "dlq_count": safe_int(dlq_row["count"] if dlq_row else 0),
                    "open_dlq_count": safe_int(dlq_row["open_count"] if dlq_row else 0),
                }
            return {
                "status": "OK" if safe_int(row["total_events"] if row else 0) > 0 else "NO_DATA",
                "total_events": safe_int(row["total_events"] if row else 0),
                "latest_event_ts": latest.isoformat() if latest else None,
                "event_lag_seconds": lag_seconds,
                **dlq,
            }

    def fetch_ai_cost_cache(self) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "INSUFFICIENT_DATA", "reason": "database_disabled"}
        with self._factory.connect() as conn:
            if not self._table_exists(conn, "ai_cost_ledger") and not self._table_exists(conn, "ai_cache"):
                return {"status": "NO_DATA", "reason": "ai_tables_missing"}
            cost_today = 0.0
            request_count = 0
            if self._table_exists(conn, "ai_cost_ledger"):
                cost_row = conn.execute(
                    """
                    SELECT COALESCE(SUM(estimated_cost), 0) AS cost_today
                    FROM ai_cost_ledger
                    WHERE created_at::date = CURRENT_DATE
                    """
                ).fetchone()
                cost_today = float(cost_row["cost_today"] or 0)
            if self._table_exists(conn, "ai_requests"):
                request_row = conn.execute(
                    "SELECT COUNT(*) AS count FROM ai_requests WHERE created_at::date = CURRENT_DATE"
                ).fetchone()
                request_count = safe_int(request_row["count"] if request_row else 0)
            cache = {"entries": 0, "hits": 0, "cache_hit_rate": None}
            if self._table_exists(conn, "ai_cache"):
                cache_row = conn.execute(
                    "SELECT COUNT(*) AS entries, COALESCE(SUM(hit_count), 0) AS hits FROM ai_cache"
                ).fetchone()
                hits = safe_int(cache_row["hits"] if cache_row else 0)
                entries = safe_int(cache_row["entries"] if cache_row else 0)
                cache = {
                    "entries": entries,
                    "hits": hits,
                    "cache_hit_rate": round(hits / max(hits + entries, 1), 4),
                }
            return {
                "status": "OK",
                "ai_cost_today": cost_today,
                "ai_requests_today": request_count,
                **cache,
                "bounded": cost_today < 10.0,
            }

    def detect_duplicates_orphans(self) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "INSUFFICIENT_DATA", "reason": "database_disabled"}
        with self._factory.connect() as conn:
            duplicate_rows: list[dict[str, Any]] = []
            orphan_orders: list[dict[str, Any]] = []
            legacy_open_positions = None

            if self._table_exists(conn, "orders_v2"):
                duplicate_rows = conn.execute(
                    """
                    SELECT order_id, market_id, side, engine
                    FROM orders_v2
                    WHERE order_status IN ('CREATED','SUBMITTED_PAPER','PLANNED_SHADOW','PARTIALLY_FILLED')
                    """
                ).fetchall()
                if self._table_exists(conn, "exit_plans"):
                    orphan_orders = conn.execute(
                        """
                        SELECT o.order_id, o.market_id, o.side, o.engine, o.order_status
                        FROM orders_v2 o
                        LEFT JOIN exit_plans p ON p.exit_plan_id = o.exit_plan_id OR p.order_id = o.order_id
                        WHERE o.order_status IN ('CREATED','SUBMITTED_PAPER','PLANNED_SHADOW','PARTIALLY_FILLED')
                          AND p.id IS NULL
                        ORDER BY o.created_at DESC
                        LIMIT 50
                        """
                    ).fetchall()

            if self._table_exists(conn, "paper_positions"):
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM paper_positions
                    WHERE current_status NOT IN ('CLOSED','CANCELLED','CANCELED','FAILED')
                    """
                ).fetchone()
                legacy_open_positions = safe_int(row["count"] if row else 0)

            duplicates = detect_duplicate_active_orders(duplicate_rows)
            return {
                "status": "OK",
                "duplicate_active_orders": duplicates,
                "duplicate_active_order_count": len(duplicates),
                "orphan_orders": [dict(row) for row in orphan_orders],
                "orphan_order_count": len(orphan_orders),
                "legacy_open_positions": legacy_open_positions,
                "legacy_position_truth": (
                    "insufficient_exit_plan_linkage" if legacy_open_positions else "no_legacy_open_positions"
                ),
                "ok": not duplicates and not orphan_orders,
            }

    def collect_checkpoint(self, *, base_url: str = "http://127.0.0.1:8000") -> dict[str, Any]:
        endpoint_results = self.fetch_endpoints(base_url, HEALTH_ENDPOINTS)
        dashboard_results = self.fetch_endpoints(base_url, DASHBOARD_ENDPOINTS)
        dashboard_payloads = {
            endpoint: result.payload or {}
            for endpoint, result in dashboard_results.items()
            if result.ok and result.payload is not None
        }
        return {
            "checkpoint_ts": utc_now_iso(),
            "counts": self.fetch_count_snapshot(),
            "pipeline": self.fetch_pipeline_counts(),
            "event_lag": self.fetch_event_lag(),
            "ai_cost_cache": self.fetch_ai_cost_cache(),
            "duplicates_orphans": self.detect_duplicates_orphans(),
            "health_endpoints": {key: value.to_dict() for key, value in endpoint_results.items()},
            "dashboard_truth": evaluate_dashboard_payloads(dashboard_payloads),
            "dashboard_endpoints": {key: value.to_dict() for key, value in dashboard_results.items()},
        }

    def build_report(
        self,
        *,
        run_id: str,
        run_type: str,
        mode: str,
        started_at: str,
        finished_at: str,
        before_counts: dict[str, int],
        after_counts: dict[str, int],
        checkpoints: list[dict[str, Any]],
    ) -> dict[str, Any]:
        safety = evaluate_no_live_mutation(before_counts, after_counts, mode)
        latest = checkpoints[-1] if checkpoints else {}
        return {
            "run_id": run_id,
            "run_type": run_type,
            "mode": mode,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": "PASS" if safety["ok"] else "FAIL",
            "before_counts": before_counts,
            "after_counts": after_counts,
            "safety_summary": safety,
            "latest_checkpoint": latest,
            "checkpoints": checkpoints,
        }

    def fetch_endpoints(self, base_url: str, endpoints: tuple[str, ...]) -> dict[str, HttpResult]:
        base_url = base_url.rstrip("/")
        return {endpoint: self._fetch_json(base_url + endpoint, endpoint) for endpoint in endpoints}

    def _fetch_json(self, url: str, endpoint: str) -> HttpResult:
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read().decode("utf-8")
                payload = json.loads(body) if body else {}
                return HttpResult(endpoint, True, response.status, payload, None)
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except Exception:
                payload = None
            return HttpResult(endpoint, False, exc.code, payload, str(exc))
        except Exception as exc:
            return HttpResult(endpoint, False, None, None, str(exc))

    def _table_count(self, conn: Any, table: str) -> int:
        if not self._table_exists(conn, table):
            return -1
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return safe_int(row["count"] if row else 0)

    def _table_exists(self, conn: Any, table: str) -> bool:
        row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
        return bool(row and row["table_name"])
