from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.registry import NeuronHealth
from app.repositories.neuron_registry_repository import NeuronRegistryRepository


SOURCE_STATUS_NEURON_BY_OWNER = {
    "source_status": "source",
    "polymarket_gamma": "market",
    "polymarket_clob_orderbook": "orderbook",
    "polymarket_clob_prices": "market",
    "polymarket_clob_spreads": "orderbook",
    "polymarket_activity_readonly": "whale",
    "ollama_local_model": "ai",
    "news_provider": "news",
    "reddit_or_social_provider": "social",
}


class NeuronRegistryService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: NeuronRegistryRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or NeuronRegistryRepository()

    def ensure_default_neurons(self) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn, conn.transaction():
            return self._repository.ensure_default_neurons(conn)

    def list_neurons(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        self.refresh_neuron_health_from_signals()
        with self._factory.connect() as conn:
            rows = self._repository.list_neurons(conn, status=status, category=category, enabled=enabled)
            stats_by_neuron = self._repository.stats_by_neuron(conn)
        return [_neuron_api(row, stats_by_neuron.get(row["neuron_name"], {})) for row in rows]

    def get_neuron(self, neuron_name: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        self.refresh_neuron_health_from_signals()
        with self._factory.connect() as conn:
            row = self._repository.get_neuron(conn, neuron_name)
            stats_by_neuron = self._repository.stats_by_neuron(conn)
        return _neuron_api(row, stats_by_neuron.get(row["neuron_name"], {})) if row else None

    def refresh_neuron_health_from_signals(self) -> int:
        if not self._factory.enabled:
            return 0
        updated = 0
        now = datetime.now(UTC)
        with self._factory.connect() as conn, conn.transaction():
            self._repository.ensure_default_neurons(conn)
            registry = self._repository.list_neurons(conn)
            stats = self._repository.stats_by_neuron(conn)
            source_statuses = self._repository.source_status_by_name(conn)
            for row in registry:
                health = self._health_for_row(row, stats.get(row["neuron_name"], {}), source_statuses, now)
                self._repository.upsert_neuron_health(conn, health)
                updated += 1
        return updated

    def get_neuron_stats(self, neuron_name: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_stats(neuron_name)
        self.refresh_neuron_health_from_signals()
        normalized = neuron_name.strip().lower()
        with self._factory.connect() as conn:
            stats = self._repository.stats_by_neuron(conn).get(normalized)
        return _stats_api(normalized, stats or {})

    def get_neuron_mesh_summary(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        self.refresh_neuron_health_from_signals()
        with self._factory.connect() as conn:
            rows = self._repository.list_neurons(conn)
            stats_by_neuron = self._repository.stats_by_neuron(conn)
        neurons = [_neuron_api(row, stats_by_neuron.get(row["neuron_name"], {})) for row in rows]
        status_counts = {status.lower() + "_neurons": 0 for status in ("ACTIVE", "PARTIAL", "DISABLED", "MISSING", "DEGRADED", "STALE")}
        for item in neurons:
            health = item["health"]["health_status"]
            key = str(health).lower() + "_neurons"
            if key in status_counts:
                status_counts[key] += 1
        signals_per_neuron = [
            {"neuron_name": item["neuron_name"], "signals_24h": item["stats"]["signals_24h"], "signals_1h": item["stats"]["signals_1h"]}
            for item in neurons
        ]
        last_signal_by_neuron = [
            {"neuron_name": item["neuron_name"], "last_signal_at": item["stats"]["last_signal_at"]}
            for item in neurons
        ]
        neuron_errors = [
            {
                "neuron_name": item["neuron_name"],
                "health_status": item["health"]["health_status"],
                "last_error": item["health"]["last_error"],
                "last_error_at": item["health"]["last_error_at"],
            }
            for item in neurons
            if item["health"]["health_status"] in {"DEGRADED", "ERROR"} or item["health"]["last_error"]
        ]
        silent_expected = [
            item["neuron_name"]
            for item in neurons
            if item["health"]["expected_to_emit"] and item["registry"]["enabled"] and not item["stats"]["last_signal_at"]
        ]
        total = len(neurons)
        return {
            "status": _mesh_status(neurons),
            "mock_data": False,
            "updated_at": datetime.now(UTC).isoformat(),
            "total_neurons": total,
            "active_neurons": status_counts["active_neurons"],
            "partial_neurons": status_counts["partial_neurons"],
            "disabled_neurons": status_counts["disabled_neurons"],
            "missing_neurons": status_counts["missing_neurons"],
            "degraded_neurons": status_counts["degraded_neurons"],
            "stale_neurons": status_counts["stale_neurons"],
            "signals_per_neuron": signals_per_neuron,
            "last_signal_by_neuron": last_signal_by_neuron,
            "neuron_errors": neuron_errors,
            "silent_expected_neurons": silent_expected,
            "neurons": neurons,
        }

    def _health_for_row(
        self,
        row: dict[str, Any],
        stats: dict[str, Any],
        source_statuses: dict[str, dict[str, Any]],
        now: datetime,
    ) -> NeuronHealth:
        enabled = bool(row["enabled"])
        stale_after = _stale_after(row)
        last_signal_at = _as_aware(stats.get("last_signal_at"))
        latest_status = str(stats.get("latest_status") or "").upper()
        source = _source_for_row(row, source_statuses)
        source_runtime = str(source.get("runtime_status") or "").upper() if source else ""
        source_freshness = str(source.get("freshness_status") or "").upper() if source else ""
        expected_to_emit = enabled and (bool(row.get("expected_signal_types")) or row.get("producer_source") in {"source_status", "rules_resolution"})
        is_stale = bool(last_signal_at and now - last_signal_at > timedelta(seconds=stale_after))
        last_error = None
        last_error_at = None
        if latest_status == "ERROR":
            last_error = "latest signal status is ERROR"
            last_error_at = last_signal_at
        elif source_runtime in {"DEGRADED", "MISSING", "ERROR"}:
            last_error = source.get("notes") or f"source status {source_runtime}"
            last_error_at = source.get("last_error_at") or source.get("updated_at")

        if not enabled:
            health_status = "DISABLED"
        elif latest_status == "ERROR" or source_runtime == "ERROR":
            health_status = "ERROR"
        elif source_runtime in {"DEGRADED", "MISSING"} or latest_status == "DEGRADED":
            health_status = "DEGRADED"
        elif is_stale:
            health_status = "STALE"
        elif last_signal_at and latest_status in {"ACTIVE", "PARTIAL", "STALE", "DISABLED", "MISSING", "DEGRADED"}:
            health_status = "ACTIVE" if latest_status == "ACTIVE" else latest_status
        elif source_runtime == "ACTIVE":
            health_status = "PARTIAL"
        elif expected_to_emit:
            health_status = row["default_status"] if row["default_status"] != "ACTIVE" else "PARTIAL"
        else:
            health_status = row["default_status"]

        return NeuronHealth(
            neuron_name=row["neuron_name"],
            runtime_status=health_status,
            health_status=health_status,
            last_signal_at=last_signal_at,
            last_success_at=last_signal_at or source.get("last_success_at") if source else last_signal_at,
            last_error_at=last_error_at,
            last_error=last_error,
            stale_after_seconds=stale_after,
            is_stale=is_stale,
            expected_to_emit=expected_to_emit,
            enabled=enabled,
            source_status_name=source.get("source_name") if source else None,
            signal_count_1h=int(stats.get("signals_1h") or 0),
            signal_count_24h=int(stats.get("signals_24h") or 0),
            error_count_24h=1 if latest_status == "ERROR" else int(source.get("error_count") or 0) if source else 0,
            updated_at=now,
        )


def _source_for_row(row: dict[str, Any], source_statuses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    owner = str(row.get("owner_component") or "")
    if owner in source_statuses:
        return source_statuses[owner]
    if row.get("neuron_name") == "source" and source_statuses:
        active = sum(1 for item in source_statuses.values() if item.get("runtime_status") == "ACTIVE")
        return {
            "source_name": "source_status",
            "runtime_status": "ACTIVE" if active else "MISSING",
            "freshness_status": "FRESH" if active else "UNKNOWN",
            "last_success_at": max((item.get("last_success_at") for item in source_statuses.values() if item.get("last_success_at")), default=None),
            "last_error_at": None,
            "error_count": sum(int(item.get("error_count") or 0) for item in source_statuses.values()),
            "notes": f"{active} active sources",
        }
    return {}


def _neuron_api(row: dict[str, Any], stats: dict[str, Any] | None = None) -> dict[str, Any]:
    stats = stats or {}
    return {
        "neuron_name": row["neuron_name"],
        "registry": {
            "display_name": row["display_name"],
            "category": row["category"],
            "description": row["description"],
            "expected_signal_types": row.get("expected_signal_types") or [],
            "producer_source": row.get("producer_source"),
            "is_required_for_paper": row.get("is_required_for_paper"),
            "is_required_for_live": row.get("is_required_for_live"),
            "default_status": row.get("default_status"),
            "enabled": row.get("enabled"),
            "owner_component": row.get("owner_component"),
            "created_at": _json_time(row.get("created_at")),
            "updated_at": _json_time(row.get("updated_at")),
        },
        "health": {
            "runtime_status": row.get("runtime_status") or row.get("default_status"),
            "health_status": row.get("health_status") or row.get("default_status"),
            "last_signal_at": _json_time(row.get("last_signal_at")),
            "last_success_at": _json_time(row.get("last_success_at")),
            "last_error_at": _json_time(row.get("last_error_at")),
            "last_error": row.get("last_error"),
            "stale_after_seconds": row.get("stale_after_seconds"),
            "is_stale": bool(row.get("is_stale")),
            "expected_to_emit": bool(row.get("expected_to_emit")) if row.get("expected_to_emit") is not None else False,
            "enabled": bool(row.get("enabled")),
            "source_status_name": row.get("source_status_name"),
            "signal_count_1h": int(row.get("signal_count_1h") or 0),
            "signal_count_24h": int(row.get("signal_count_24h") or 0),
            "error_count_24h": int(row.get("error_count_24h") or 0),
            "updated_at": _json_time(row.get("health_updated_at")),
        },
        "stats": _stats_api(row["neuron_name"], stats),
    }


def _stats_api(neuron_name: str, stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "neuron_name": neuron_name,
        "total_signals": int(stats.get("total_signals") or 0),
        "signals_1m": int(stats.get("signals_1m") or 0),
        "signals_5m": int(stats.get("signals_5m") or 0),
        "signals_1h": int(stats.get("signals_1h") or 0),
        "signals_24h": int(stats.get("signals_24h") or 0),
        "last_signal_at": _json_time(stats.get("last_signal_at")),
        "active_market_count": int(stats.get("active_market_count") or 0),
        "stale_signal_count": int(stats.get("stale_signal_count") or 0),
        "unprocessed_signal_count": int(stats.get("unprocessed_signal_count") or 0),
        "latest_status": stats.get("latest_status"),
        "updated_at": _json_time(stats.get("updated_at")),
    }


def _mesh_status(neurons: list[dict[str, Any]]) -> str:
    statuses = {str(item["health"]["health_status"]) for item in neurons}
    if statuses & {"ERROR", "DEGRADED", "STALE", "MISSING"}:
        return "DEGRADED"
    return "OK"


def _stale_after(row: dict[str, Any]) -> int:
    producer = row.get("producer_source")
    if producer == "source_status":
        return 300
    if producer == "rules_resolution":
        return 3600
    return 86400


def _as_aware(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return None


def _json_time(value: Any) -> str | None:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()
    return value if isinstance(value, str) else None


def _empty_stats(neuron_name: str) -> dict[str, Any]:
    return _stats_api(neuron_name, {})


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "OK",
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "total_neurons": 0,
        "active_neurons": 0,
        "partial_neurons": 0,
        "disabled_neurons": 0,
        "missing_neurons": 0,
        "degraded_neurons": 0,
        "stale_neurons": 0,
        "signals_per_neuron": [],
        "last_signal_by_neuron": [],
        "neuron_errors": [],
        "silent_expected_neurons": [],
        "neurons": [],
    }
