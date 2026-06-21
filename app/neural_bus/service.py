from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.mesh_sessions.service import MeshSessionService
from app.neural_bus.contracts import NeuralEvent
from app.neural_bus.errors import NeuralDeliveryBlocked, NeuralPublishBlocked
from app.neural_bus.repository import NeuralEventRepository, table_exists
from app.neural_bus.types import NeuralEventType, list_event_registry, validate_neural_event_type
from app.services.system_power import SystemPowerService


SOURCE_EVENT_MAPPINGS: tuple[dict[str, Any], ...] = (
    {"table": "news_normalized_events", "id": "news_event_id", "event_type": NeuralEventType.NEWS_DETECTED.value, "component": "News Neuron", "source_type": "neuron", "priority": 3},
    {"table": "whale_events", "id": "whale_event_id", "event_type": NeuralEventType.WHALE_DETECTED.value, "component": "Whale Neuron", "source_type": "neuron", "priority": 4},
    {"table": "social_normalized_events", "id": "social_event_id", "event_type": NeuralEventType.SOCIAL_SPIKE.value, "component": "Social Neuron", "source_type": "neuron", "priority": 4},
    {"table": "market_snapshots", "id": "id", "event_type": NeuralEventType.MARKET_REPRICING.value, "component": "Market Neuron", "source_type": "market", "priority": 5},
    {"table": "liquidity_snapshots", "id": "id", "event_type": NeuralEventType.LIQUIDITY_CHANGED.value, "component": "Liquidity Neuron", "source_type": "neuron", "priority": 5},
    {"table": "market_snapshots", "id": "id", "event_type": NeuralEventType.SPREAD_CHANGED.value, "component": "Market Neuron", "source_type": "market", "priority": 5, "requires_any": ("spread", "best_bid", "best_ask")},
    {"table": "orderbook_snapshots", "id": "id", "event_type": NeuralEventType.ORDERBOOK_REFRESHED.value, "component": "Orderbook Neuron", "source_type": "neuron", "priority": 4},
    {"table": "deterministic_side_evidence", "id": "id", "event_type": NeuralEventType.SIDE_DETERMINED.value, "component": "Side Evidence", "source_type": "neuron", "priority": 4},
    {"table": "trusted_orderbook_evidence_links", "id": "id", "event_type": NeuralEventType.TRUSTED_ORDERBOOK_CREATED.value, "component": "Orderbook Neuron", "source_type": "neuron", "priority": 3},
    {"table": "risk_decisions", "id": "risk_decision_id", "event_type": NeuralEventType.RISK_CHANGED.value, "component": "Risk", "source_type": "risk", "priority": 2},
    {"table": "exit_plans", "id": "exit_plan_id", "event_type": NeuralEventType.EXIT_CHANGED.value, "component": "Exit", "source_type": "exit", "priority": 2},
    {"table": "paper_eligibility_candidates", "id": "eligibility_id", "event_type": NeuralEventType.ELIGIBILITY_CHANGED.value, "component": "Eligibility", "source_type": "eligibility", "priority": 3},
    {"table": "paper_intents", "id": "paper_intent_id", "event_type": NeuralEventType.PAPER_INTENT_CREATED.value, "component": "Paper Intent", "source_type": "paper", "priority": 2},
    {"table": "paper_positions", "id": "id", "event_type": NeuralEventType.POSITION_OPENED.value, "component": "Position Neuron", "source_type": "paper", "priority": 2},
    {"table": "paper_positions", "id": "id", "event_type": NeuralEventType.POSITION_CLOSED.value, "component": "Position Neuron", "source_type": "paper", "priority": 2, "requires_any": ("closed_at",)},
    {"table": "paper_daily_pnl", "id": "id", "event_type": NeuralEventType.PNL_CHANGED.value, "component": "PnL Ledger", "source_type": "paper", "priority": 3},
    {"table": "paper_capital_ledger", "id": "ledger_id", "event_type": NeuralEventType.CAPITAL_CHANGED.value, "component": "Capital Neuron", "source_type": "capital", "priority": 3},
    {"table": "no_trade_log", "id": "no_trade_id", "event_type": NeuralEventType.NO_TRADE_RECORDED.value, "component": "No-Trade Intelligence", "source_type": "paper", "priority": 2},
    {"table": "brain_outputs", "id": "brain_output_id", "event_type": NeuralEventType.AI_CONTEXT_UPDATED.value, "component": "Brain", "source_type": "brain", "priority": 4},
    {"table": "ai_decision_logs", "id": "decision_id", "event_type": NeuralEventType.AI_CONTEXT_UPDATED.value, "component": "AI Brain", "source_type": "brain", "priority": 4},
    {"table": "market_memory_v2", "id": "memory_id", "event_type": NeuralEventType.MEMORY_UPDATED.value, "component": "Market Memory", "source_type": "memory", "priority": 5},
)


class NeuralEventBusService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: NeuralEventRepository | None = None,
        mesh_sessions: MeshSessionService | None = None,
        system_power: SystemPowerService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or NeuralEventRepository()
        self._mesh_sessions = mesh_sessions or MeshSessionService(connection_factory=self._factory)
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)

    def publish_event(
        self,
        event_type: NeuralEventType | str,
        *,
        source_component: str,
        source_type: str,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        market_id: str | None = None,
        candidate_id: str | None = None,
        position_id: str | None = None,
        priority: int = 5,
        source_table: str | None = None,
        source_record_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            raise NeuralPublishBlocked("DATABASE_UNAVAILABLE")
        self._assert_system_on("publish")
        event = NeuralEvent(
            event_type=validate_neural_event_type(event_type),
            correlation_id=correlation_id,
            market_id=market_id,
            candidate_id=candidate_id,
            position_id=position_id,
            source_component=source_component,
            source_type=source_type,
            priority=priority,
            payload_json=payload or {},
            source_table=source_table,
            source_record_id=source_record_id,
            metadata_json=metadata or {},
        )
        with self._factory.connect() as conn, conn.transaction():
            row = self._repository.append_event(conn, event)
            self._mesh_sessions.resolve_event_with_conn(conn, row)
            return row

    def register_consumer(
        self,
        *,
        consumer_name: str,
        event_types: list[NeuralEventType | str],
        source_component: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = [validate_neural_event_type(event_type) for event_type in event_types]
        with self._factory.connect() as conn, conn.transaction():
            return self._repository.register_consumer(
                conn,
                consumer_name=consumer_name,
                event_types=normalized,
                source_component=source_component,
                metadata=metadata,
            )

    def deliver_pending(self, *, limit: int = 100) -> dict[str, int | str]:
        if not self._factory.enabled:
            raise NeuralDeliveryBlocked("DATABASE_UNAVAILABLE")
        self._assert_system_on("delivery")
        delivered = 0
        checked = 0
        with self._factory.connect() as conn, conn.transaction():
            events = self._repository.list_events(conn, limit=limit)
            for event in reversed(events):
                checked += 1
                consumers = self._repository.interested_consumers(conn, event)
                for consumer in consumers:
                    row = self._repository.record_delivery(
                        conn,
                        event=event,
                        consumer=consumer,
                        delivery_status="DELIVERED",
                        metadata={"foundation_delivery": True, "business_logic_attached": False},
                    )
                    if row:
                        delivered += 1
        return {"status": "OK", "events_checked": checked, "deliveries_recorded": delivered}

    def replay_events(
        self,
        *,
        requested_by: str,
        reason: str,
        event_type: NeuralEventType | str | None = None,
        event_id: str | None = None,
        start_id: int | None = None,
        end_id: int | None = None,
        market_id: str | None = None,
        correlation_id: str | None = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        self._assert_system_on("replay")
        filters = {
            key: value
            for key, value in {
                "event_type": validate_neural_event_type(event_type) if event_type else None,
                "event_id": event_id,
                "start_id": start_id,
                "end_id": end_id,
                "market_id": market_id,
                "correlation_id": correlation_id,
            }.items()
            if value is not None
        }
        with self._factory.connect() as conn, conn.transaction():
            replay_id = self._repository.create_replay(
                conn,
                requested_by=requested_by,
                reason=reason,
                filters=filters,
            )
            self._repository.update_replay(
                conn,
                replay_id=replay_id,
                status="RUNNING",
                matched_count=0,
                delivered_count=0,
                started_at=True,
            )
            events = self._repository.list_events(conn, limit=limit, **filters)
            delivered = 0
            failed = 0
            for event in reversed(events):
                for consumer in self._repository.interested_consumers(conn, event):
                    try:
                        self._repository.record_delivery(
                            conn,
                            event=event,
                            consumer=consumer,
                            replay_id=replay_id,
                            delivery_status="REPLAYED",
                            metadata={"replay": True},
                        )
                        delivered += 1
                    except Exception:
                        failed += 1
            self._repository.update_replay(
                conn,
                replay_id=replay_id,
                status="COMPLETED" if failed == 0 else "FAILED",
                matched_count=len(events),
                delivered_count=delivered,
                failed_count=failed,
                finished_at=True,
            )
        return {
            "mock_data": False,
            "status": "COMPLETED" if failed == 0 else "FAILED",
            "replay_id": replay_id,
            "matched_count": len(events),
            "delivered_count": delivered,
            "failed_count": failed,
            "filters": filters,
        }

    def publish_source_backed_events(self, *, cycle_id: str | None = None, limit_per_source: int = 50) -> dict[str, Any]:
        self._assert_system_on("publish")
        created = 0
        scanned_sources = 0
        with self._factory.connect() as conn, conn.transaction():
            for spec in SOURCE_EVENT_MAPPINGS:
                if not table_exists(conn, spec["table"]):
                    continue
                scanned_sources += 1
                rows = conn.execute(
                    f"SELECT * FROM {spec['table']} ORDER BY id DESC LIMIT %s",
                    (limit_per_source,),
                ).fetchall()
                for row in rows:
                    row = dict(row)
                    if not _required_source_present(row, spec):
                        continue
                    event = NeuralEvent(
                        event_type=spec["event_type"],
                        correlation_id=str(row.get("correlation_id") or cycle_id) if (row.get("correlation_id") or cycle_id) else None,
                        market_id=_first_text(row, "market_id", "polymarket_market_id"),
                        candidate_id=_first_text(row, "candidate_id", "eligibility_id"),
                        position_id=_first_text(row, "position_id", "paper_position_id", "id") if spec["table"] == "paper_positions" else _first_text(row, "position_id", "paper_position_id"),
                        source_component=spec["component"],
                        source_type=spec["source_type"],
                        priority=int(spec["priority"]),
                        payload_json=row,
                        source_table=spec["table"],
                        source_record_id=str(row.get(spec["id"]) or row.get("id")),
                        metadata_json={"source_backed": True, "cycle_id": cycle_id},
                    )
                    before = conn.execute("SELECT COUNT(*) AS count FROM neural_events").fetchone()["count"]
                    row_event = self._repository.append_event(conn, event)
                    self._mesh_sessions.resolve_event_with_conn(conn, row_event)
                    after = conn.execute("SELECT COUNT(*) AS count FROM neural_events").fetchone()["count"]
                    created += max(0, int(after or 0) - int(before or 0))
        return {"mock_data": False, "status": "OK", "events_created": created, "sources_scanned": scanned_sources}

    def dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard("DB_UNAVAILABLE")
        with self._factory.connect() as conn:
            if not table_exists(conn, "neural_events"):
                return _empty_dashboard("MISSING_TABLES")
            summary = self._repository.dashboard_summary(conn, limit=limit)
            power = self._system_power.get_power_state()
        summary.update(
            {
                "mock_data": False,
                "status": "OK",
                "system_power": power.get("power"),
                "publishing_allowed": bool(power.get("runtime_work_allowed")),
                "delivery_allowed": bool(power.get("runtime_work_allowed")),
                "registry": list_event_registry(),
                "generated_at": datetime.now(UTC).isoformat(),
            }
        )
        return summary

    def list_events(self, *, limit: int = 100, event_type: str | None = None) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return self._repository.list_events(conn, limit=limit, event_type=event_type)

    def _assert_system_on(self, action: str) -> None:
        power = self._system_power.get_power_state()
        if str(power.get("power") or "OFF").upper() != "ON" or not power.get("runtime_work_allowed"):
            if action == "delivery":
                raise NeuralDeliveryBlocked("SYSTEM_POWER_OFF")
            raise NeuralPublishBlocked("SYSTEM_POWER_OFF")


def _required_source_present(row: dict[str, Any], spec: dict[str, Any]) -> bool:
    for key in spec.get("requires_any") or ():
        if row.get(key) not in (None, "", []):
            return True
    return not spec.get("requires_any")


def _first_text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _empty_dashboard(status: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "events_last_hour": 0,
        "events_last_day": 0,
        "event_types": [],
        "active_consumers": 0,
        "consumer_lag": [],
        "failed_deliveries": 0,
        "latest_events": [],
        "registry": list_event_registry(),
    }
