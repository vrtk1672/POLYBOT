from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.correlation import new_correlation_id
from app.neural_mesh.contracts import NeuronSignal, signal_from_row
from app.neural_mesh.lineage import SignalLineage
from app.repositories.neuron_signal_repository import NeuronSignalRepository
from app.repositories.signal_lineage_repository import SignalLineageRepository


SOURCE_TO_NEURON = {
    "market_discovery": "market",
    "orderbook": "orderbook",
    "prices": "market",
    "spreads": "orderbook",
    "activity": "whale",
    "local_ai": "ai",
    "news": "news",
    "social": "social",
}

SOURCE_STATUS_MAP = {
    "ACTIVE": "ACTIVE",
    "DEGRADED": "DEGRADED",
    "MISSING": "MISSING",
    "DISABLED": "DISABLED",
}


class NeuronSignalService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: NeuronSignalRepository | None = None,
        lineage_repository: SignalLineageRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or NeuronSignalRepository()
        self._lineage_repository = lineage_repository or SignalLineageRepository()

    def create_signal(self, signal: NeuronSignal | dict[str, Any]) -> dict[str, Any]:
        item = signal if isinstance(signal, NeuronSignal) else NeuronSignal(**signal)
        if not self._factory.enabled:
            return item.to_api_dict()
        with self._factory.connect() as conn, conn.transaction():
            row = self._repository.create_signal(conn, item)
        return signal_from_row(row).to_api_dict()

    def create_signal_with_lineage(self, signal: NeuronSignal | dict[str, Any], lineage: dict[str, Any]) -> dict[str, Any]:
        item = signal if isinstance(signal, NeuronSignal) else NeuronSignal(**signal)
        if not self._factory.enabled:
            return item.to_api_dict()
        with self._factory.connect() as conn, conn.transaction():
            row = self._repository.create_signal(conn, item)
            created = signal_from_row(row)
            lineage_item = _lineage_for_created_signal(created, lineage)
            if lineage_item.source_status_id is None and lineage_item.source_name:
                lineage_item.source_status_id = self._lineage_repository.source_status_id(conn, lineage_item.source_name)
            self._lineage_repository.attach_signal_binding(conn, lineage_item)
        return created.to_api_dict()

    def attach_signal_binding(self, signal_id: str, lineage: dict[str, Any]) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn, conn.transaction():
            signal_row = conn.execute("SELECT * FROM neuron_signals WHERE signal_id = %s", (signal_id,)).fetchone()
            if not signal_row:
                return None
            signal = signal_from_row(dict(signal_row))
            lineage_item = _lineage_for_created_signal(signal, lineage)
            if lineage_item.source_status_id is None and lineage_item.source_name:
                lineage_item.source_status_id = self._lineage_repository.source_status_id(conn, lineage_item.source_name)
            bound = self._lineage_repository.attach_signal_binding(conn, lineage_item)
        return dict(bound)

    def list_recent_signals(
        self,
        *,
        limit: int = 50,
        neuron: str | None = None,
        market_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_recent_signals(
                conn,
                limit=limit,
                neuron=neuron,
                market_id=market_id,
                status=status,
            )
        return [signal_from_row(dict(row)).to_api_dict() for row in rows]

    def list_market_signals(self, market_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_market_signals(conn, market_id, limit=limit)
        return [signal_from_row(dict(row)).to_api_dict() for row in rows]

    def list_neuron_signals(self, neuron_name: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_neuron_signals(conn, neuron_name, limit=limit)
        return [signal_from_row(dict(row)).to_api_dict() for row in rows]

    def get_signal_summary(self, *, limit: int = 10) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        return {
            "signals_per_minute": summary["signals_per_minute"],
            "total_signals_24h": summary["total_signals_24h"],
            "signals_by_neuron": [_json_safe(dict(row)) for row in summary["signals_by_neuron"]],
            "latest_signals": [_json_safe(signal_from_row(dict(row)).to_api_dict()) for row in summary["latest_signals"]],
            "stale_signals": [_json_safe(signal_from_row(dict(row)).to_api_dict()) for row in summary["stale_signals"]],
            "unprocessed_signals": summary["unprocessed_signals"],
        }

    def mark_processed(self, signal_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn, conn.transaction():
            row = self._repository.mark_processed(conn, signal_id)
        return signal_from_row(row).to_api_dict() if row else None

    def record_source_status_signals(self, sources: list[dict[str, Any]]) -> int:
        signals = [source_status_to_signal(item) for item in sources]
        lineages = [_source_status_lineage(signal, source) for signal, source in zip(signals, sources, strict=False)]
        return self._record_many(signals, lineages=lineages)

    def record_rules_status_signals(self, markets: list[dict[str, Any]]) -> int:
        signals = [rules_status_to_signal(item) for item in markets]
        lineages = [_rules_status_lineage(signal, market) for signal, market in zip(signals, markets, strict=False)]
        return self._record_many(signals, lineages=lineages)

    def _record_many(self, signals: list[NeuronSignal], *, lineages: list[dict[str, Any]] | None = None) -> int:
        if not signals:
            return 0
        if not self._factory.enabled:
            return 0
        created = 0
        with self._factory.connect() as conn, conn.transaction():
            for index, signal in enumerate(signals):
                row = self._repository.create_signal(conn, signal)
                created_signal = signal_from_row(row)
                if lineages and index < len(lineages):
                    lineage_item = _lineage_for_created_signal(created_signal, lineages[index])
                    if lineage_item.source_status_id is None and lineage_item.source_name:
                        lineage_item.source_status_id = self._lineage_repository.source_status_id(conn, lineage_item.source_name)
                    self._lineage_repository.attach_signal_binding(conn, lineage_item)
                created += 1
        return created


def source_status_to_signal(source: dict[str, Any]) -> NeuronSignal:
    source_type = str(source.get("source_type") or "unknown").lower()
    runtime_status = str(source.get("runtime_status") or "MISSING").upper()
    freshness_status = str(source.get("freshness_status") or "UNKNOWN").upper()
    status = SOURCE_STATUS_MAP.get(runtime_status, "ERROR")
    if status == "ACTIVE" and freshness_status == "STALE":
        status = "STALE"
    confidence = 1.0 if source.get("configured") is True or runtime_status == "DISABLED" else 0.5
    details = source.get("details_json") if isinstance(source.get("details_json"), dict) else {}
    evidence = {
        "source_type": source_type,
        "runtime_status": runtime_status,
        "freshness_status": freshness_status,
        "configured": bool(source.get("configured")),
        "read_only": bool(source.get("read_only")),
        "mutation_allowed": bool(source.get("mutation_allowed")),
        "latency_ms": source.get("latency_ms"),
        "notes": source.get("notes"),
        "details": details,
    }
    market_id = details.get("sample_market_id") if isinstance(details.get("sample_market_id"), str) else None
    correlation_id = source.get("correlation_id") or new_correlation_id()
    return NeuronSignal(
        neuron=SOURCE_TO_NEURON.get(source_type, "unknown"),
        event_type="source_status_observed",
        source_name=source.get("source_name"),
        market_id=market_id,
        correlation_id=correlation_id,
        raw_direction="neutral",
        strength=_status_strength(status),
        confidence=confidence,
        source_reliability=1.0 if status == "ACTIVE" else 0.25 if status in {"MISSING", "ERROR"} else 0.5,
        freshness_seconds=0 if status == "ACTIVE" else None,
        status=status,
        evidence=evidence,
        raw_payload_ref=f"source_status:{source.get('source_name')}",
        stale_after_seconds=300 if status == "ACTIVE" else None,
    )


def rules_status_to_signal(market: dict[str, Any]) -> NeuronSignal:
    resolution_status = str(market.get("resolution_source_status") or "MISSING").upper()
    source_status = str(market.get("source_verification_status") or "").upper()
    hard_block = bool(market.get("hard_block") or market.get("resolution_source_hard_block"))
    status = "DEGRADED" if hard_block else "PARTIAL"
    if resolution_status == "EXPLICIT" and source_status in {"VERIFIED", "CLEAR", ""}:
        status = "ACTIVE"
    elif resolution_status == "MISSING":
        status = "MISSING"
    elif resolution_status == "AMBIGUOUS":
        status = "DEGRADED"
    penalty = _bounded(market.get("penalty") or market.get("resolution_source_penalty"))
    confidence = _bounded(market.get("resolution_source_confidence"))
    evidence = {
        "question": market.get("question"),
        "market_family": market.get("market_family"),
        "rules_text_present": bool(market.get("rules_text_present")),
        "resolution_source_status": resolution_status,
        "resolution_source_type": market.get("resolution_source_type"),
        "resolution_source_name": market.get("resolution_source_name"),
        "source_verification_status": source_status or None,
        "wording_risk": market.get("wording_risk"),
        "dispute_risk": market.get("dispute_risk"),
        "resolution_clarity": market.get("resolution_clarity"),
        "hard_block": hard_block,
        "evidence": market.get("evidence"),
    }
    correlation_id = market.get("correlation_id") or new_correlation_id()
    return NeuronSignal(
        neuron="rules",
        event_type="rules_resolution_status_observed",
        source_name="rules_resolution_truth",
        market_id=market.get("market_id"),
        correlation_id=correlation_id,
        raw_direction="neutral",
        strength=penalty,
        confidence=confidence,
        source_reliability=confidence,
        freshness_seconds=0 if market.get("analyzed_at") else None,
        status=status,
        evidence=evidence,
        raw_payload_ref=f"rules_analysis:{market.get('rules_analysis_id')}" if market.get("rules_analysis_id") else None,
        stale_after_seconds=3600,
    )


def _status_strength(status: str) -> float:
    return {
        "ACTIVE": 1.0,
        "PARTIAL": 0.65,
        "DEGRADED": 0.35,
        "STALE": 0.25,
        "DISABLED": 0.0,
        "MISSING": 0.0,
        "ERROR": 0.0,
    }.get(status, 0.0)


def _bounded(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _empty_summary() -> dict[str, Any]:
    return {
        "signals_per_minute": 0.0,
        "total_signals_24h": 0,
        "signals_by_neuron": [],
        "latest_signals": [],
        "stale_signals": [],
        "unprocessed_signals": 0,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _lineage_for_created_signal(signal: NeuronSignal, lineage: dict[str, Any]) -> SignalLineage:
    data = dict(lineage)
    data.setdefault("signal_id", signal.signal_id)
    data.setdefault("neuron_name", signal.neuron)
    data.setdefault("source_name", signal.source_name)
    data.setdefault("market_id", signal.market_id)
    data.setdefault("correlation_id", signal.correlation_id)
    data.setdefault("raw_payload_ref", signal.raw_payload_ref)
    data.setdefault("generated_from", "unknown")
    return SignalLineage(**data)


def _source_status_lineage(signal: NeuronSignal, source: dict[str, Any]) -> dict[str, Any]:
    source_name = str(source.get("source_name") or "")
    producer = "clob_source_status_adapter" if source_name.startswith("polymarket_clob") else "source_status_adapter"
    return {
        "producer_name": producer,
        "producer_component": "app.services.neuron_signals",
        "producer_version": "v2_part1c",
        "source_name": source_name or signal.source_name,
        "source_event_id": source.get("source_event_id"),
        "market_id": signal.market_id,
        "correlation_id": signal.correlation_id,
        "raw_payload_ref": signal.raw_payload_ref,
        "generated_from": "source_status",
        "lineage": {
            "source_type": source.get("source_type"),
            "runtime_status": source.get("runtime_status"),
            "freshness_status": source.get("freshness_status"),
            "correlation_id_generated": source.get("correlation_id") is None,
            "raw_payload_policy": "reference_only",
        },
    }


def _rules_status_lineage(signal: NeuronSignal, market: dict[str, Any]) -> dict[str, Any]:
    return {
        "producer_name": "rules_resolution_adapter",
        "producer_component": "app.services.neuron_signals",
        "producer_version": "v2_part1c",
        "source_name": "rules_resolution_truth",
        "source_event_id": market.get("rules_analysis_id"),
        "market_id": signal.market_id,
        "correlation_id": signal.correlation_id,
        "raw_payload_ref": signal.raw_payload_ref,
        "generated_from": "rules_resolution",
        "lineage": {
            "resolution_source_status": market.get("resolution_source_status"),
            "source_verification_status": market.get("source_verification_status"),
            "correlation_id_generated": market.get("correlation_id") is None,
            "raw_payload_policy": "reference_only",
        },
    }
