from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.mesh_sessions.repository import MeshSessionRepository, table_exists
from app.mesh_sessions.types import MeshSessionType, is_adverse_event, is_opportunity_event
from app.services.system_power import SystemPowerService


STALE_AFTER = timedelta(hours=24)


class MeshSessionBlocked(RuntimeError):
    pass


class MeshSessionService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: MeshSessionRepository | None = None,
        system_power: SystemPowerService | None = None,
        stale_after: timedelta = STALE_AFTER,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or MeshSessionRepository()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._stale_after = stale_after

    def resolve_event(self, event: dict[str, Any]) -> dict[str, Any]:
        self._assert_system_on()
        if not self._factory.enabled:
            raise MeshSessionBlocked("DATABASE_UNAVAILABLE")
        with self._factory.connect() as conn, conn.transaction():
            return self.resolve_event_with_conn(conn, event)

    def resolve_event_with_conn(self, conn: Any, event: dict[str, Any]) -> dict[str, Any]:
        if not table_exists(conn, "mesh_sessions"):
            return {"mock_data": False, "status": "MISSING_TABLES", "sessions_linked": 0, "session_ids": []}
        specs = self._session_specs(event)
        linked = 0
        created_or_seen: list[str] = []
        linked_session_ids: list[str] = []
        for spec in specs:
            session = self._repository.upsert_session(conn, spec=spec, event=event)
            inserted = self._repository.link_event(
                conn,
                session_id=session["session_id"],
                event=event,
                role=spec["role"],
                metadata={"resolver": "v3_mesh_sessions_foundation"},
            )
            if inserted:
                self._repository.upsert_participant(
                    conn,
                    session_id=session["session_id"],
                    component=str(event.get("source_component") or "Unknown"),
                    component_type=str(event.get("source_type") or "unknown"),
                    metadata={"event_type": event.get("event_type")},
                )
                self._repository.upsert_state(conn, session_id=session["session_id"], updates=_state_updates(event))
                self._repository.mark_closed_if_needed(conn, session_id=session["session_id"], event=event)
            self._repository.recompute_session_counts(conn, session["session_id"])
            linked += int(inserted)
            created_or_seen.append(session["session_id"])
            if inserted:
                linked_session_ids.append(session["session_id"])
        if linked_session_ids:
            from app.shared_awareness.service import SharedAwarenessService

            awareness = SharedAwarenessService(connection_factory=self._factory)
            for session_id in dict.fromkeys(linked_session_ids):
                awareness.refresh_session_with_conn(conn, session_id)
        return {
            "mock_data": False,
            "status": "OK",
            "sessions_resolved": len(specs),
            "sessions_linked": linked,
            "session_ids": created_or_seen,
        }

    def materialize_unlinked_events(self, *, limit: int = 250) -> dict[str, Any]:
        self._assert_system_on()
        with self._factory.connect() as conn, conn.transaction():
            events = self._repository.list_unlinked_events(conn, limit=limit)
            linked = 0
            session_ids: list[str] = []
            for event in events:
                result = self.resolve_event_with_conn(conn, event)
                linked += int(result.get("sessions_linked") or 0)
                session_ids.extend(result.get("session_ids") or [])
        return {"mock_data": False, "status": "OK", "events_checked": len(events), "sessions_linked": linked, "session_ids": session_ids}

    def dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard("DB_UNAVAILABLE")
        with self._factory.connect() as conn, conn.transaction():
            if not table_exists(conn, "mesh_sessions"):
                return _empty_dashboard("MISSING_TABLES")
            payload = self._repository.dashboard_summary(conn, limit=limit, stale_after=self._stale_after)
        payload.update({"mock_data": False, "status": "OK", "generated_at": datetime.now(UTC).isoformat()})
        return payload

    def session_detail(self, session_id: str, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DB_UNAVAILABLE", "session_id": session_id}
        with self._factory.connect() as conn:
            if not table_exists(conn, "mesh_sessions"):
                return {"mock_data": False, "status": "MISSING_TABLES", "session_id": session_id}
            payload = self._repository.session_detail(conn, session_id, limit=limit)
        if payload is None:
            return {"mock_data": False, "status": "NOT_FOUND", "session_id": session_id}
        payload.update({"mock_data": False, "status": "OK", "generated_at": datetime.now(UTC).isoformat()})
        return payload

    def _session_specs(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        market_id = _text(event.get("market_id"))
        candidate_id = _text(event.get("candidate_id"))
        position_id = _text(event.get("position_id"))
        correlation_id = _text(event.get("correlation_id"))
        event_type = str(event.get("event_type") or "")
        adverse = is_adverse_event(event)
        opportunity = is_opportunity_event(event)
        specs: list[dict[str, Any]] = []
        if position_id:
            specs.append(_spec(MeshSessionType.POSITION_SESSION, "PRIMARY", event, position_id=position_id, market_id=market_id, candidate_id=candidate_id, correlation_id=correlation_id, threat=adverse, opportunity=opportunity))
        elif candidate_id:
            specs.append(_spec(MeshSessionType.CANDIDATE_SESSION, "PRIMARY", event, candidate_id=candidate_id, market_id=market_id, correlation_id=correlation_id, threat=adverse, opportunity=opportunity))
        elif market_id:
            specs.append(_spec(MeshSessionType.MARKET_SESSION, "PRIMARY", event, market_id=market_id, correlation_id=correlation_id, threat=adverse, opportunity=opportunity))
        elif correlation_id:
            specs.append(_spec(MeshSessionType.GLOBAL_SESSION, "GLOBAL", event, correlation_id=correlation_id, threat=adverse, opportunity=opportunity))
        else:
            specs.append(_spec(MeshSessionType.UNASSIGNED_SESSION, "OBSERVATION", event, threat=adverse, opportunity=opportunity))

        context_key = position_id or candidate_id or market_id or correlation_id or str(event.get("event_id"))
        if adverse:
            specs.append(_spec(MeshSessionType.THREAT_SESSION, "THREAT", event, market_id=market_id, candidate_id=candidate_id, position_id=position_id, correlation_id=correlation_id, context_key=context_key, threat=True, opportunity=False))
        if opportunity:
            specs.append(_spec(MeshSessionType.OPPORTUNITY_SESSION, "OPPORTUNITY", event, market_id=market_id, candidate_id=candidate_id, position_id=position_id, correlation_id=correlation_id, context_key=context_key, threat=False, opportunity=True))
        return _dedupe_specs(specs)

    def _assert_system_on(self) -> None:
        power = self._system_power.get_power_state()
        if str(power.get("power") or "OFF").upper() != "ON" or not power.get("runtime_work_allowed"):
            raise MeshSessionBlocked("SYSTEM_POWER_OFF")


def _spec(
    session_type: MeshSessionType,
    role: str,
    event: dict[str, Any],
    *,
    market_id: str | None = None,
    candidate_id: str | None = None,
    position_id: str | None = None,
    correlation_id: str | None = None,
    context_key: str | None = None,
    threat: bool = False,
    opportunity: bool = False,
) -> dict[str, Any]:
    key = context_key or position_id or candidate_id or market_id or correlation_id or str(event.get("event_id"))
    session_id = _session_id(session_type.value, key)
    title_entity = position_id or candidate_id or market_id or correlation_id or key
    return {
        "session_id": session_id,
        "session_type": session_type.value,
        "market_id": market_id,
        "candidate_id": candidate_id,
        "position_id": position_id,
        "correlation_id": correlation_id,
        "title": f"{session_type.value} {title_entity}",
        "threat_context": threat,
        "opportunity_context": opportunity,
        "role": role,
        "metadata_json": {
            "identity_key": key,
            "created_from_event_type": event.get("event_type"),
            "created_from_event_id": event.get("event_id"),
        },
    }


def _session_id(session_type: str, key: str) -> str:
    digest = hashlib.sha256(f"{session_type}:{key}".encode("utf-8")).hexdigest()[:24]
    return f"mesh_session_{session_type.lower()}_{digest}"


def _state_updates(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "")
    payload = event.get("payload_json") if isinstance(event.get("payload_json"), dict) else {}
    snapshot = {
        "event_id": event.get("event_id"),
        "event_type": event_type,
        "source_component": event.get("source_component"),
        "created_at": _text(event.get("created_at")),
        "payload": payload,
    }
    updates: dict[str, Any] = {}
    if event.get("market_id"):
        updates["latest_market_state_json"] = snapshot
    if event.get("candidate_id"):
        updates["latest_candidate_state_json"] = snapshot
    if event.get("position_id") or event_type in {"POSITION_OPENED", "POSITION_CLOSED"}:
        updates["latest_position_state_json"] = snapshot
    if event_type == "RISK_CHANGED":
        updates["latest_risk_state_json"] = snapshot
    if event_type in {"EXIT_CHANGED", "POSITION_CLOSED"}:
        updates["latest_exit_state_json"] = snapshot
    if event_type == "CAPITAL_CHANGED":
        updates["latest_capital_state_json"] = snapshot
    if event_type == "NEWS_DETECTED":
        updates["latest_news_state_json"] = snapshot
    if event_type in {"LIQUIDITY_CHANGED", "ORDERBOOK_REFRESHED", "TRUSTED_ORDERBOOK_CREATED", "SPREAD_CHANGED"}:
        updates["latest_liquidity_state_json"] = snapshot
    if "time" in payload or "time_to_resolution" in payload:
        updates["latest_time_state_json"] = snapshot
    if "fee" in payload or "fees" in payload or event_type == "CAPITAL_CHANGED":
        updates["latest_fees_state_json"] = snapshot
    if "rules" in payload or "wording" in payload:
        updates["latest_rules_state_json"] = snapshot
    return updates


def _dedupe_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for spec in specs:
        if spec["session_id"] in seen:
            continue
        seen.add(spec["session_id"])
        result.append(spec)
    return result


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _empty_dashboard(status: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "total_sessions": 0,
        "active_sessions": 0,
        "market_sessions": 0,
        "candidate_sessions": 0,
        "position_sessions": 0,
        "opportunity_sessions": 0,
        "threat_sessions": 0,
        "global_sessions": 0,
        "unassigned_sessions": 0,
        "sessions_with_multiple_events": 0,
        "sessions_with_multiple_participants": 0,
        "latest_sessions": [],
        "top_active_sessions": [],
        "stale_sessions": [],
        "orphan_events_without_session": 0,
        "event_to_session_coverage": {"total_events": 0, "linked_events": 0, "coverage_pct": 100.0},
    }
