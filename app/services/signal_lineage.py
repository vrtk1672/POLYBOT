from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.contracts import signal_from_row
from app.neural_mesh.lineage import SignalLineage
from app.repositories.signal_lineage_repository import SignalLineageRepository


class SignalLineageService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: SignalLineageRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or SignalLineageRepository()

    def get_signal_lineage(self, signal_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_signal_lineage(conn, signal_id)
        return _lineage_response(row) if row else None

    def list_signals_by_correlation_id(self, correlation_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_signals_by_correlation_id(conn, correlation_id, limit=limit)
        return [_lineage_response(row) for row in rows]

    def list_signals_by_source(self, source_name: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_signals_by_source(conn, source_name, limit=limit)
        return [_lineage_response(row) for row in rows]

    def list_signals_by_producer(self, producer_name: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_signals_by_producer(conn, producer_name, limit=limit)
        return [_lineage_response(row) for row in rows]

    def list_unbound_signals(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_unbound_signals(conn, limit=limit)
        return [_lineage_response(row) for row in rows]

    def get_lineage_summary(self, *, limit: int = 10) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.get_lineage_summary(conn, limit=limit)
        return {
            "status": "OK" if summary["unbound_signals_24h"] == 0 else "DEGRADED",
            "mock_data": False,
            "updated_at": datetime.now(UTC).isoformat(),
            "total_signals_24h": summary["total_signals_24h"],
            "bound_signals_24h": summary["bound_signals_24h"],
            "unbound_signals_24h": summary["unbound_signals_24h"],
            "bound_pct_24h": summary["bound_pct_24h"],
            "signals_by_producer": [_json_safe(dict(row)) for row in summary["signals_by_producer"]],
            "signals_by_source": [_json_safe(dict(row)) for row in summary["signals_by_source"]],
            "signals_without_correlation_id": summary["signals_without_correlation_id"],
            "signals_without_raw_payload_ref": summary["signals_without_raw_payload_ref"],
            "latest_unbound_signals": [_lineage_response(row) for row in summary["latest_unbound_signals"]],
        }


def _lineage_response(row: dict[str, Any]) -> dict[str, Any]:
    signal = signal_from_row(dict(row)).to_api_dict()
    lineage = {
        "producer_name": row.get("producer_name"),
        "producer_component": row.get("producer_component"),
        "producer_version": row.get("producer_version"),
        "source_name": row.get("binding_source_name") or row.get("source_name"),
        "event_log_id": row.get("event_log_id"),
        "source_status_id": row.get("source_status_id"),
        "source_event_id": row.get("source_event_id"),
        "market_id": row.get("binding_market_id") or row.get("market_id"),
        "correlation_id": row.get("binding_correlation_id") or row.get("correlation_id"),
        "raw_payload_ref": row.get("binding_raw_payload_ref") or row.get("raw_payload_ref"),
        "generated_from": row.get("generated_from") or "unknown",
        "lineage": row.get("lineage_json") or {},
        "binding_created_at": row.get("binding_created_at"),
    }
    return {"signal_id": signal["signal_id"], "signal": signal, "lineage": _json_safe(lineage)}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "OK",
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "total_signals_24h": 0,
        "bound_signals_24h": 0,
        "unbound_signals_24h": 0,
        "bound_pct_24h": 0.0,
        "signals_by_producer": [],
        "signals_by_source": [],
        "signals_without_correlation_id": 0,
        "signals_without_raw_payload_ref": 0,
        "latest_unbound_signals": [],
    }
