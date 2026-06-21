from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.mesh_sessions.service import MeshSessionService
from app.neural_bus.errors import NeuralPublishBlocked
from app.neural_bus.service import NeuralEventBusService
from app.neural_bus.types import NeuralEventType
from app.services.brain_dialogue import BrainDialogueService
from app.services.system_power import SystemPowerService


def _prepare() -> NeuralEventBusService:
    run_migrations()
    return NeuralEventBusService()


def _session_for_event(event_id: str, session_type: str | None = None) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        where = "se.event_id = %s"
        params: list[object] = [event_id]
        if session_type:
            where += " AND s.session_type = %s"
            params.append(session_type)
        row = conn.execute(
            f"""
            SELECT s.*
            FROM mesh_sessions s
            JOIN mesh_session_events se ON se.session_id = s.session_id
            WHERE {where}
            ORDER BY s.id
            LIMIT 1
            """,
            params,
        ).fetchone()
    assert row is not None
    return dict(row)


def _count(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM " + table).fetchone()
    return int(row["count"] or 0)


def test_market_event_creates_market_session_and_participant(postgres_test_schema) -> None:
    service = _prepare()

    event = service.publish_event(
        NeuralEventType.ORDERBOOK_REFRESHED,
        source_component="Orderbook",
        source_type="neuron",
        market_id="market-session-1",
        payload={"best_bid": 0.42, "best_ask": 0.44},
    )

    session = _session_for_event(event["event_id"], "MARKET_SESSION")
    assert session["market_id"] == "market-session-1"
    assert session["event_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        participant = conn.execute(
            """
            SELECT *
            FROM mesh_session_participants
            WHERE session_id = %s AND component = 'Orderbook'
            """,
            (session["session_id"],),
        ).fetchone()
    assert participant is not None
    assert participant["component_type"] == "neuron"


def test_candidate_and_position_events_create_entity_sessions(postgres_test_schema) -> None:
    service = _prepare()

    candidate_event = service.publish_event(
        NeuralEventType.ELIGIBILITY_CHANGED,
        source_component="Eligibility",
        source_type="eligibility",
        market_id="market-session-2",
        candidate_id="candidate-session-1",
        payload={"status": "ELIGIBLE"},
    )
    position_event = service.publish_event(
        NeuralEventType.POSITION_OPENED,
        source_component="Position Neuron",
        source_type="paper",
        market_id="market-session-2",
        candidate_id="candidate-session-1",
        position_id="position-session-1",
        payload={"status": "OPEN"},
    )

    candidate_session = _session_for_event(candidate_event["event_id"], "CANDIDATE_SESSION")
    position_session = _session_for_event(position_event["event_id"], "POSITION_SESSION")
    assert candidate_session["candidate_id"] == "candidate-session-1"
    assert position_session["position_id"] == "position-session-1"


def test_adverse_position_event_marks_threat_context(postgres_test_schema) -> None:
    service = _prepare()

    event = service.publish_event(
        NeuralEventType.RISK_CHANGED,
        source_component="Risk",
        source_type="risk",
        market_id="market-threat-1",
        candidate_id="candidate-threat-1",
        position_id="position-threat-1",
        payload={"decision": "BLOCK", "threat_context": True},
    )

    position_session = _session_for_event(event["event_id"], "POSITION_SESSION")
    threat_session = _session_for_event(event["event_id"], "THREAT_SESSION")
    assert position_session["threat_context"] is True
    assert threat_session["threat_context"] is True


def test_positive_signal_marks_opportunity_context(postgres_test_schema) -> None:
    service = _prepare()

    event = service.publish_event(
        NeuralEventType.TRUSTED_ORDERBOOK_CREATED,
        source_component="Orderbook",
        source_type="neuron",
        market_id="market-opportunity-1",
        payload={"opportunity_context": True, "status": "TRUSTED"},
    )

    market_session = _session_for_event(event["event_id"], "MARKET_SESSION")
    opportunity_session = _session_for_event(event["event_id"], "OPPORTUNITY_SESSION")
    assert market_session["opportunity_context"] is True
    assert opportunity_session["opportunity_context"] is True


def test_unassigned_event_creates_unassigned_session(postgres_test_schema) -> None:
    service = _prepare()

    event = service.publish_event(
        NeuralEventType.AI_CONTEXT_UPDATED,
        source_component="Brain",
        source_type="brain",
        payload={"summary": "global context without entity"},
    )

    session = _session_for_event(event["event_id"], "UNASSIGNED_SESSION")
    assert session["market_id"] is None
    assert session["candidate_id"] is None
    assert session["position_id"] is None


def test_same_event_is_not_linked_twice(postgres_test_schema) -> None:
    service = _prepare()
    event = service.publish_event(
        NeuralEventType.NEWS_DETECTED,
        source_component="News Neuron",
        source_type="neuron",
        market_id="market-idempotent-1",
        payload={"headline": "idempotent"},
    )

    result = MeshSessionService().resolve_event(event)

    with DatabaseConnectionFactory().connect() as conn:
        links = conn.execute(
            "SELECT COUNT(*) AS count FROM mesh_session_events WHERE event_id = %s",
            (event["event_id"],),
        ).fetchone()["count"]
    assert result["sessions_linked"] == 0
    assert links == 1


def test_session_becomes_active_after_multiple_events(postgres_test_schema) -> None:
    service = _prepare()
    market_id = "market-active-1"

    service.publish_event(
        NeuralEventType.ORDERBOOK_REFRESHED,
        source_component="Orderbook",
        source_type="neuron",
        market_id=market_id,
        payload={"snapshot": 1},
    )
    event = service.publish_event(
        NeuralEventType.LIQUIDITY_CHANGED,
        source_component="Liquidity",
        source_type="neuron",
        market_id=market_id,
        payload={"liquidity": 1000},
    )

    session = _session_for_event(event["event_id"], "MARKET_SESSION")
    assert session["status"] == "ACTIVE"
    assert session["event_count"] == 2
    assert session["participant_count"] == 2


def test_dashboard_summary_and_detail_return_truth(postgres_test_schema) -> None:
    service = _prepare()
    event = service.publish_event(
        NeuralEventType.ORDERBOOK_REFRESHED,
        source_component="Orderbook",
        source_type="neuron",
        market_id="dashboard-session-market",
        payload={"snapshot_status": "OK"},
    )
    session = _session_for_event(event["event_id"], "MARKET_SESSION")
    client = TestClient(create_app())

    summary = client.get("/dashboard/api/v2/mesh-sessions?limit=10")
    detail = client.get(f"/dashboard/api/v2/mesh-sessions/{session['session_id']}?limit=10")

    assert summary.status_code == 200
    assert detail.status_code == 200
    summary_payload = summary.json()
    detail_payload = detail.json()
    assert summary_payload["mock_data"] is False
    assert summary_payload["total_sessions"] >= 1
    assert summary_payload["event_to_session_coverage"]["linked_events"] >= 1
    assert detail_payload["mock_data"] is False
    assert detail_payload["session"]["session_id"] == session["session_id"]
    assert detail_payload["event_timeline"][0]["event_id"] == event["event_id"]


def test_system_off_blocks_session_creation_from_publish(postgres_test_schema) -> None:
    service = _prepare()
    SystemPowerService().turn_off(actor="pytest", reason="mesh session publish blocked")

    with pytest.raises(NeuralPublishBlocked):
        service.publish_event(
            NeuralEventType.ORDERBOOK_REFRESHED,
            source_component="Orderbook",
            source_type="neuron",
            market_id="blocked-market",
            payload={"snapshot": "blocked"},
        )

    assert _count("neural_events") == 0
    assert _count("mesh_sessions") == 0
    assert _count("mesh_session_events") == 0


def test_mesh_sessions_do_not_mutate_paper_live_or_execution_truth(postgres_test_schema) -> None:
    service = _prepare()
    before = {
        "live_orders": _count("live_orders"),
        "paper_orders": _count("paper_orders"),
        "paper_fills": _count("paper_fills"),
        "paper_positions": _count("paper_positions"),
        "orders_v2": _count("orders_v2"),
        "fills_v2": _count("fills_v2"),
        "positions": _count("positions"),
    }

    service.publish_event(
        NeuralEventType.RISK_CHANGED,
        source_component="Risk",
        source_type="risk",
        market_id="safety-market",
        candidate_id="safety-candidate",
        position_id="safety-position",
        payload={"decision": "BLOCK"},
    )

    after = {table: _count(table) for table in before}
    assert after == before


def test_brain_dialogue_materializes_source_backed_session_messages(postgres_test_schema) -> None:
    service = _prepare()
    event = service.publish_event(
        NeuralEventType.ORDERBOOK_REFRESHED,
        source_component="Orderbook",
        source_type="neuron",
        market_id="dialogue-session-market",
        payload={"snapshot_status": "OK"},
    )
    session = _session_for_event(event["event_id"], "MARKET_SESSION")

    result = BrainDialogueService().materialize_recent(limit_per_source=50)
    feed = BrainDialogueService().list_events(limit=50, component="Mesh Session")

    assert result["status"] == "OK"
    messages = [row["human_message"] for row in feed["events"]]
    assert any("Opened MARKET_SESSION" in message for message in messages)
    assert any("Linked ORDERBOOK_REFRESHED" in message for message in messages)
    assert any(row["raw_payload_json"].get("session_id") == session["session_id"] for row in feed["events"])
