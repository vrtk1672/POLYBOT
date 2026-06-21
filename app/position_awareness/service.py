from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.position_awareness.repository import PositionAwarenessRepository, table_exists
from app.position_awareness.types import PositionReactionType
from app.services.system_power import SystemPowerService


AGING_THRESHOLD_MINUTES = 12 * 60


class PositionAwarenessBlocked(RuntimeError):
    pass


class PositionAwarenessService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: PositionAwarenessRepository | None = None,
        system_power: SystemPowerService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or PositionAwarenessRepository()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)

    def refresh_position(self, position_id: str) -> dict[str, Any]:
        self._assert_system_on()
        with self._factory.connect() as conn, conn.transaction():
            position = self._repository.get_position(conn, position_id)
            if not position:
                return {"mock_data": False, "status": "POSITION_NOT_FOUND", "position_id": position_id}
            session = self._repository.ensure_position_session(conn, position)
            return self._refresh_with_conn(conn, position=position, session=session)

    def refresh_active_positions(self, *, limit: int = 100) -> dict[str, Any]:
        self._assert_system_on()
        refreshed = 0
        with self._factory.connect() as conn, conn.transaction():
            if not self._tables_ready(conn):
                return {"mock_data": False, "status": "MISSING_TABLES", "positions_refreshed": 0}
            positions = self._repository.list_active_positions(conn, limit=limit)
            for position in positions:
                session = self._repository.ensure_position_session(conn, position)
                result = self._refresh_with_conn(conn, position=position, session=session)
                refreshed += int(result.get("status") == "OK")
        return {"mock_data": False, "status": "OK", "positions_checked": len(positions), "positions_refreshed": refreshed}

    def refresh_session_with_conn(self, conn: Any, session_id: str) -> dict[str, Any]:
        if not self._tables_ready(conn):
            return {"mock_data": False, "status": "MISSING_TABLES", "session_id": session_id}
        session = self._repository.get_session(conn, session_id)
        if not session:
            return {"mock_data": False, "status": "SESSION_NOT_FOUND", "session_id": session_id}
        position_id = session.get("position_id")
        if not position_id:
            return {"mock_data": False, "status": "NOT_POSITION_SESSION", "session_id": session_id}
        position = self._repository.get_position(conn, str(position_id))
        if not position:
            return {"mock_data": False, "status": "POSITION_NOT_FOUND", "session_id": session_id, "position_id": position_id}
        return self._refresh_with_conn(conn, position=position, session=session)

    def dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard("DB_UNAVAILABLE")
        with self._factory.connect() as conn:
            if not table_exists(conn, "position_awareness"):
                return _empty_dashboard("MISSING_TABLES")
            rows = self._repository.dashboard_rows(conn, limit=limit)
            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(AVG(awareness_score), 0) AS avg_score,
                    COUNT(*) FILTER (WHERE risk_status IN ('CAUTION','BLOCK','WORSENED')) AS risk_watch,
                    COUNT(*) FILTER (WHERE exit_status IN ('CAUTION','EXIT_REVIEW','DEGRADED')) AS exit_watch,
                    COUNT(*) FILTER (WHERE capital_status IN ('CAPITAL_BLOCK','CAPITAL_RELEASE_REVIEW','CAPITAL_WATCH')) AS capital_watch
                FROM position_awareness
                """
            ).fetchone()
            reactions = conn.execute(
                """
                SELECT reaction_type, COUNT(*) AS count
                FROM position_reactions
                GROUP BY reaction_type
                ORDER BY count DESC, reaction_type
                """
            ).fetchall()
            open_positions = 0
            if table_exists(conn, "paper_positions"):
                open_positions = int(
                    conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM paper_positions
                        WHERE current_status IN ('OPEN','EXIT_PENDING')
                          AND closed_at IS NULL
                          AND COALESCE(excluded_from_active_paper_truth, false) = false
                        """
                    ).fetchone()["count"]
                    or 0
                )
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": datetime.now(UTC).isoformat(),
                "total_position_awareness": int(totals["total"] or 0),
                "active_open_positions": open_positions,
                "avg_awareness_score": round(float(totals["avg_score"] or 0), 4),
                "positions_with_risk_watch": int(totals["risk_watch"] or 0),
                "positions_with_exit_watch": int(totals["exit_watch"] or 0),
                "positions_with_capital_watch": int(totals["capital_watch"] or 0),
                "reaction_counts": {str(row["reaction_type"]): int(row["count"] or 0) for row in reactions},
                "latest_awareness": rows,
            }
        )

    def detail(self, position_id: str, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DB_UNAVAILABLE", "position_id": position_id}
        with self._factory.connect() as conn:
            if not table_exists(conn, "position_awareness"):
                return {"mock_data": False, "status": "MISSING_TABLES", "position_id": position_id}
            payload = self._repository.detail(conn, position_id, limit=limit)
        if payload is None:
            return {"mock_data": False, "status": "NOT_FOUND", "position_id": position_id}
        payload.update({"mock_data": False, "status": "OK", "generated_at": datetime.now(UTC).isoformat()})
        return _json_safe(payload)

    def _refresh_with_conn(self, conn: Any, *, position: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
        awareness_source = self._repository.shared_awareness(conn, str(session["session_id"]))
        capital = self._repository.latest_capital_evaluation(conn, str(session["session_id"]))
        coordinator = self._repository.latest_coordinator_decision(conn, str(session["session_id"]))
        events = self._repository.linked_events(conn, str(session["session_id"]))
        awareness, reactions, sources = _build_position_awareness(
            position=position,
            session=session,
            awareness=awareness_source,
            capital=capital,
            coordinator=coordinator,
            events=events,
        )
        row = self._repository.upsert_awareness(conn, awareness, reactions=reactions, sources=sources)
        return {
            "mock_data": False,
            "status": "OK",
            "position_id": row["position_id"],
            "session_id": row["session_id"],
            "awareness_id": row["awareness_id"],
            "reactions_created_or_updated": len(reactions),
        }

    def _tables_ready(self, conn: Any) -> bool:
        return all(
            table_exists(conn, table)
            for table in (
                "mesh_sessions",
                "position_awareness",
                "position_reactions",
                "position_context_sources",
            )
        )

    def _assert_system_on(self) -> None:
        power = self._system_power.get_power_state()
        if str(power.get("power") or "OFF").upper() != "ON" or not power.get("runtime_work_allowed"):
            raise PositionAwarenessBlocked("SYSTEM_POWER_OFF")


def _build_position_awareness(
    *,
    position: dict[str, Any],
    session: dict[str, Any],
    awareness: dict[str, Any] | None,
    capital: dict[str, Any] | None,
    coordinator: dict[str, Any] | None,
    events: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    position_id = str(position["id"])
    session_id = str(session["session_id"])
    entry = _decimal(position.get("avg_entry"))
    current = _decimal(position.get("mark_price"))
    size = _decimal(position.get("size"))
    exposure = entry * size if entry is not None and size is not None else None
    pnl = _position_pnl(position)
    pnl_pct = (pnl / exposure * Decimal("100")) if pnl is not None and exposure and exposure != 0 else None
    age_minutes = _age_minutes(position.get("opened_at"))
    reactions: list[dict[str, Any]] = []
    sources = [
        _source(position_id, session_id, "paper_positions", position_id, "POSITION", f"paper position status={position.get('current_status')}")
    ]
    if awareness:
        sources.append(_source(position_id, session_id, "mesh_shared_awareness", str(awareness["awareness_id"]), "AWARENESS", "shared awareness context for position"))
    if capital:
        sources.append(_source(position_id, session_id, "capital_brain_evaluations", str(capital["evaluation_id"]), "CAPITAL", f"capital decision={capital.get('decision')}"))
    if coordinator:
        sources.append(_source(position_id, session_id, "mesh_coordinator_decisions", str(coordinator["decision_id"]), "COORDINATOR", f"coordinator action={coordinator.get('final_action')}"))

    if pnl is not None:
        if pnl > 0:
            reactions.append(_reaction(position_id, session_id, PositionReactionType.PNL_RISING, source_event_id=f"paper_positions:{position_id}", source_domain="PNL", source_component="Position", severity="INFO", summary=f"PnL improved to {pnl}."))
        elif pnl < 0:
            reactions.append(_reaction(position_id, session_id, PositionReactionType.PNL_FALLING, source_event_id=f"paper_positions:{position_id}", source_domain="PNL", source_component="Position", severity="WARN", summary=f"PnL deteriorated to {pnl}."))
    if age_minutes is not None and age_minutes >= AGING_THRESHOLD_MINUTES:
        reactions.append(_reaction(position_id, session_id, PositionReactionType.POSITION_AGING, source_event_id=f"paper_positions:{position_id}", source_domain="POSITION", source_component="Position", severity="INFO", summary=f"Position age is {age_minutes} minutes."))

    for event in events:
        reactions.extend(_event_reactions(position_id=position_id, session_id=session_id, event=event))
        sources.append(_source(position_id, session_id, "neural_events", str(event["event_id"]), _event_domain(event), f"{event.get('event_type')} from {event.get('source_component')}"))

    risk_status = _risk_status(awareness, events)
    exit_status = _exit_status(awareness, events)
    capital_status = str(capital.get("decision")) if capital else "UNKNOWN"
    coordinator_status = str(coordinator.get("final_action")) if coordinator else "UNKNOWN"
    liquidity_status = _liquidity_status(awareness, events)
    if capital and capital.get("decision") in {"CAPITAL_BLOCK", "CAPITAL_RELEASE_REVIEW", "CAPITAL_WATCH"}:
        severity = "WARN" if capital.get("decision") != "CAPITAL_BLOCK" else "CRITICAL"
        reactions.append(_reaction(position_id, session_id, PositionReactionType.CAPITAL_PRESSURE, source_event_id=f"capital_brain_evaluations:{capital['evaluation_id']}", source_domain="CAPITAL", source_component="Capital Brain", severity=severity, summary=f"Capital Brain produced {capital.get('decision')}: {capital.get('reason')}"))

    if not reactions:
        reactions.append(_reaction(position_id, session_id, PositionReactionType.NO_REACTION, source_event_id=f"paper_positions:{position_id}", source_domain="POSITION", source_component="Position Awareness", severity="INFO", summary="Position Awareness found no adverse or positive reaction trigger."))

    reaction_types = {reaction["reaction_type"] for reaction in reactions}
    score = _awareness_score(reaction_types, awareness=awareness, capital=capital, coordinator=coordinator)
    row = {
        "awareness_id": f"position_awareness_{position_id}",
        "position_id": position_id,
        "session_id": session_id,
        "market_id": position.get("market_id") or session.get("market_id"),
        "side": position.get("intended_outcome"),
        "entry_price": entry,
        "current_price": current,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "exposure": exposure,
        "age_minutes": age_minutes,
        "liquidity_status": liquidity_status,
        "risk_status": risk_status,
        "exit_status": exit_status,
        "capital_status": capital_status,
        "coordinator_status": coordinator_status,
        "awareness_score": score,
    }
    return row, _dedupe_reactions(reactions), _dedupe_sources(sources)


def _event_reactions(*, position_id: str, session_id: str, event: dict[str, Any]) -> list[dict[str, Any]]:
    event_type = str(event.get("event_type") or "")
    payload = event.get("payload_json") if isinstance(event.get("payload_json"), dict) else {}
    text = " ".join(str(value) for value in [event_type, payload, event.get("source_component")] if value).upper()
    component = str(event.get("source_component") or "Neural Event")
    event_id = str(event.get("event_id"))
    if event_type == "NEWS_DETECTED":
        adverse = any(token in text for token in ("ADVERSE", "NEGATIVE", "AGAINST", "BAD", "RISK", "WORSEN"))
        return [
            _reaction(
                position_id,
                session_id,
                PositionReactionType.ADVERSE_NEWS if adverse else PositionReactionType.POSITIVE_NEWS,
                source_event_id=event_id,
                source_domain="NEWS",
                source_component=component,
                severity="WARN" if adverse else "INFO",
                summary=f"Position received {'adverse' if adverse else 'positive'} news event {event_id}.",
            )
        ]
    if event_type == "WHALE_DETECTED":
        exiting = any(token in text for token in ("EXIT", "SELL", "REDUCE", "OUTFLOW", "DUMP"))
        return [
            _reaction(position_id, session_id, PositionReactionType.WHALE_EXIT if exiting else PositionReactionType.WHALE_ENTRY, source_event_id=event_id, source_domain="WHALE", source_component=component, severity="WARN" if exiting else "INFO", summary=f"Whale {'exit' if exiting else 'entry'} signal observed for position.")
        ]
    if event_type == "LIQUIDITY_CHANGED":
        drop = any(token in text for token in ("DROP", "LOW", "WORSE", "DETERIOR", "THIN"))
        return [
            _reaction(position_id, session_id, PositionReactionType.LIQUIDITY_DROP if drop else PositionReactionType.LIQUIDITY_IMPROVED, source_event_id=event_id, source_domain="LIQUIDITY", source_component=component, severity="WARN" if drop else "INFO", summary="Liquidity deteriorated." if drop else "Liquidity improved.")
        ]
    if event_type == "SPREAD_CHANGED":
        widened = any(token in text for token in ("WIDE", "WIDEN", "WORSE", "HIGH"))
        return [
            _reaction(position_id, session_id, PositionReactionType.SPREAD_WIDENED if widened else PositionReactionType.SPREAD_IMPROVED, source_event_id=event_id, source_domain="LIQUIDITY", source_component=component, severity="WARN" if widened else "INFO", summary="Spread widened." if widened else "Spread improved.")
        ]
    if event_type == "RISK_CHANGED":
        increased = any(token in text for token in ("INCREASE", "WORSE", "BLOCK", "CAUTION", "ADVERSE", "HIGH"))
        return [
            _reaction(position_id, session_id, PositionReactionType.RISK_INCREASED if increased else PositionReactionType.RISK_DECREASED, source_event_id=event_id, source_domain="RISK", source_component=component, severity="WARN" if increased else "INFO", summary="Risk increased." if increased else "Risk decreased.")
        ]
    if event_type == "EXIT_CHANGED":
        degraded = any(token in text for token in ("DEGRADE", "WORSE", "EXIT_REQUIRED", "BLOCK", "ADVERSE"))
        return [
            _reaction(position_id, session_id, PositionReactionType.EXIT_DEGRADED if degraded else PositionReactionType.EXIT_IMPROVED, source_event_id=event_id, source_domain="EXIT", source_component=component, severity="WARN" if degraded else "INFO", summary="Exit context degraded." if degraded else "Exit context improved.")
        ]
    if event_type == "PNL_CHANGED":
        falling = any(token in text for token in ("FALL", "DOWN", "LOSS", "NEGATIVE", "DETERIOR"))
        return [
            _reaction(position_id, session_id, PositionReactionType.PNL_FALLING if falling else PositionReactionType.PNL_RISING, source_event_id=event_id, source_domain="PNL", source_component=component, severity="WARN" if falling else "INFO", summary="PnL falling." if falling else "PnL rising.")
        ]
    if event_type == "CAPITAL_CHANGED":
        pressure = any(token in text for token in ("LOCK", "PRESSURE", "BLOCK", "RELEASE", "WATCH"))
        if pressure:
            return [
                _reaction(position_id, session_id, PositionReactionType.CAPITAL_PRESSURE, source_event_id=event_id, source_domain="CAPITAL", source_component=component, severity="WARN", summary="Capital pressure observed.")
            ]
    if event_type == "POSITION_ORDERBOOK_REFRESHED":
        return [
            _reaction(position_id, session_id, PositionReactionType.POSITION_ORDERBOOK_REFRESHED, source_event_id=event_id, source_domain="ORDERBOOK", source_component=component, severity="INFO", summary="Open position token orderbook refreshed.")
        ]
    if event_type == "POSITION_EXIT_RISK":
        return [
            _reaction(position_id, session_id, PositionReactionType.POSITION_EXIT_RISK, source_event_id=event_id, source_domain="EXIT", source_component=component, severity="WARN", summary="Open position exit risk increased.")
        ]
    if event_type == "TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION":
        return [
            _reaction(position_id, session_id, PositionReactionType.TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION, source_event_id=event_id, source_domain="ORDERBOOK", source_component=component, severity="CRITICAL", summary="Open position token book unavailable.")
        ]
    if event_type == "EXIT_REVIEW":
        return [
            _reaction(position_id, session_id, PositionReactionType.EXIT_REVIEW, source_event_id=event_id, source_domain="EXIT", source_component=component, severity="WARN", summary="Open position needs exit review.")
        ]
    if event_type == "HOLD_REVIEW":
        return [
            _reaction(position_id, session_id, PositionReactionType.HOLD_REVIEW, source_event_id=event_id, source_domain="EXIT", source_component=component, severity="INFO", summary="Open position reviewed as stable.")
        ]
    if event_type == "TOKEN_IDENTITY_DRIFT_REVIEW":
        return [
            _reaction(position_id, session_id, PositionReactionType.TOKEN_IDENTITY_DRIFT_REVIEW, source_event_id=event_id, source_domain="RISK", source_component=component, severity="CRITICAL", summary="Locked position token differs from current identity.")
        ]
    if event_type == "MISSING_POSITION_TOKEN":
        return [
            _reaction(position_id, session_id, PositionReactionType.MISSING_POSITION_TOKEN, source_event_id=event_id, source_domain="POSITION", source_component=component, severity="CRITICAL", summary="Position token could not be locked from entry truth.")
        ]
    return []


def _reaction(
    position_id: str,
    session_id: str,
    reaction_type: PositionReactionType,
    *,
    source_event_id: str | None,
    source_domain: str,
    source_component: str,
    severity: str,
    summary: str,
) -> dict[str, Any]:
    source_key = source_event_id or source_domain
    return {
        "reaction_id": f"position_reaction_{position_id}_{reaction_type.value}_{_slug(source_key)}",
        "position_id": position_id,
        "session_id": session_id,
        "reaction_type": reaction_type.value,
        "source_event_id": source_event_id,
        "source_domain": source_domain,
        "source_component": source_component,
        "severity": severity,
        "summary": summary,
    }


def _source(position_id: str, session_id: str, table: str, record_id: str, domain: str, summary: str) -> dict[str, Any]:
    return {
        "position_id": position_id,
        "session_id": session_id,
        "source_table": table,
        "source_record_id": record_id,
        "source_domain": domain,
        "contribution_summary": summary,
    }


def _risk_status(awareness: dict[str, Any] | None, events: list[dict[str, Any]]) -> str:
    text = _domain_text(awareness, "risk_state_json", events, {"RISK_CHANGED"})
    if any(token in text for token in ("BLOCK", "HIGH", "WORSEN", "INCREASE", "ADVERSE")):
        return "WORSENED"
    if any(token in text for token in ("CAUTION", "WATCH")):
        return "CAUTION"
    if text:
        return "STABLE"
    return "UNKNOWN"


def _exit_status(awareness: dict[str, Any] | None, events: list[dict[str, Any]]) -> str:
    text = _domain_text(awareness, "exit_state_json", events, {"EXIT_CHANGED"})
    if any(token in text for token in ("EXIT_REQUIRED", "DEGRADE", "WORSEN", "BLOCK")):
        return "DEGRADED"
    if any(token in text for token in ("CAUTION", "WATCH")):
        return "CAUTION"
    if text:
        return "STABLE"
    return "UNKNOWN"


def _liquidity_status(awareness: dict[str, Any] | None, events: list[dict[str, Any]]) -> str:
    text = _domain_text(awareness, "liquidity_state_json", events, {"LIQUIDITY_CHANGED", "SPREAD_CHANGED", "ORDERBOOK_REFRESHED"})
    if any(token in text for token in ("STALE", "DROP", "LOW", "WIDEN", "THIN", "DETERIOR")):
        return "DETERIORATED"
    if text:
        return "STABLE"
    return "UNKNOWN"


def _domain_text(awareness: dict[str, Any] | None, column: str, events: list[dict[str, Any]], event_types: set[str]) -> str:
    parts: list[str] = []
    if awareness and isinstance(awareness.get(column), dict):
        state = awareness[column]
        parts.extend([str(state.get("status") or ""), str(state.get("summary") or "")])
    for event in events:
        if str(event.get("event_type") or "") in event_types:
            parts.append(str(event.get("payload_json") or ""))
    return " ".join(parts).upper()


def _awareness_score(
    reaction_types: set[str],
    *,
    awareness: dict[str, Any] | None,
    capital: dict[str, Any] | None,
    coordinator: dict[str, Any] | None,
) -> Decimal:
    score = Decimal("0.55")
    if awareness:
        score += Decimal("0.15")
    if capital:
        score += Decimal("0.10")
    if coordinator:
        score += Decimal("0.10")
    if reaction_types & {"ADVERSE_NEWS", "WHALE_EXIT", "LIQUIDITY_DROP", "SPREAD_WIDENED", "RISK_INCREASED", "EXIT_DEGRADED", "CAPITAL_PRESSURE", "PNL_FALLING"}:
        score -= Decimal("0.20")
    if reaction_types & {"PNL_RISING", "POSITIVE_NEWS", "LIQUIDITY_IMPROVED", "SPREAD_IMPROVED", "RISK_DECREASED", "EXIT_IMPROVED"}:
        score += Decimal("0.05")
    return max(Decimal("0"), min(Decimal("1"), score))


def _position_pnl(position: dict[str, Any]) -> Decimal | None:
    unrealized = _decimal(position.get("unrealized"))
    realized = _decimal(position.get("realized"))
    if unrealized is None and realized is None:
        return None
    return (unrealized or Decimal("0")) + (realized or Decimal("0"))


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _age_minutes(opened_at: Any) -> int | None:
    if not opened_at:
        return None
    value = opened_at
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - value.astimezone(UTC)).total_seconds() // 60))


def _event_domain(event: dict[str, Any]) -> str:
    mapping = {
        "NEWS_DETECTED": "NEWS",
        "WHALE_DETECTED": "WHALE",
        "LIQUIDITY_CHANGED": "LIQUIDITY",
        "SPREAD_CHANGED": "LIQUIDITY",
        "ORDERBOOK_REFRESHED": "ORDERBOOK",
        "POSITION_ORDERBOOK_REFRESHED": "ORDERBOOK",
        "POSITION_EXIT_RISK": "EXIT",
        "TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION": "ORDERBOOK",
        "EXIT_REVIEW": "EXIT",
        "HOLD_REVIEW": "EXIT",
        "TOKEN_IDENTITY_DRIFT_REVIEW": "RISK",
        "MISSING_POSITION_TOKEN": "POSITION",
        "RISK_CHANGED": "RISK",
        "EXIT_CHANGED": "EXIT",
        "PNL_CHANGED": "PNL",
        "CAPITAL_CHANGED": "CAPITAL",
    }
    return mapping.get(str(event.get("event_type") or ""), "EVENT")


def _dedupe_reactions(reactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for reaction in reactions:
        result[str(reaction["reaction_id"])] = reaction
    return list(result.values())


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for source in sources:
        result[
            (
                str(source["position_id"]),
                str(source["session_id"]),
                str(source["source_table"]),
                str(source["source_record_id"]),
                str(source["source_domain"]),
            )
        ] = source
    return list(result.values())


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower())[:120]


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def _empty_dashboard(status: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "total_position_awareness": 0,
        "active_open_positions": 0,
        "avg_awareness_score": 0,
        "positions_with_risk_watch": 0,
        "positions_with_exit_watch": 0,
        "positions_with_capital_watch": 0,
        "reaction_counts": {},
        "latest_awareness": [],
    }
