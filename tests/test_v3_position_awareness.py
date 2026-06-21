from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.neural_bus.errors import NeuralPublishBlocked
from app.neural_bus.service import NeuralEventBusService
from app.neural_bus.types import NeuralEventType
from app.position_awareness.service import PositionAwarenessBlocked, PositionAwarenessService
from app.services.brain_dialogue import BrainDialogueService
from app.services.system_power import SystemPowerService
from app.shared_awareness.service import SharedAwarenessService


def _prepare() -> None:
    run_migrations()


def _count(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
        if not exists:
            return 0
        return int(conn.execute("SELECT COUNT(*) AS count FROM " + table).fetchone()["count"] or 0)


def _insert_position(
    slug: str,
    *,
    unrealized: str = "1.25",
    realized: str = "0",
    opened_minutes_ago: int = 30,
    status: str = "OPEN",
) -> str:
    run_id = str(uuid4())
    position_id = str(uuid4())
    market_id = f"position-market-{slug}"
    opened_at = datetime.now(UTC) - timedelta(minutes=opened_minutes_ago)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_runs (id, mode, started_at, status, metadata_json)
            VALUES (%s, 'PAPER', now(), 'COMPLETED', %s)
            """,
            (run_id, Jsonb({"test": "v3.6"})),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size,
                avg_entry, mark_price, unrealized, realized, current_status,
                thesis_state, invalidation_state, opened_at, updated_at,
                closed_at, payload_json
            )
            VALUES (
                %s, %s, %s, 'YES', 10, 0.20, 0.30, %s, %s, %s,
                'VALID', 'NONE', %s, now(), NULL, %s
            )
            """,
            (position_id, run_id, market_id, unrealized, realized, status, opened_at, Jsonb({"test": "v3.6"})),
        )
    return position_id


def _awareness(position_id: str) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM position_awareness WHERE position_id=%s", (position_id,)).fetchone()
    assert row is not None
    return dict(row)


def _reactions(position_id: str) -> set[str]:
    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute("SELECT reaction_type FROM position_reactions WHERE position_id=%s", (position_id,)).fetchall()
    return {str(row["reaction_type"]) for row in rows}


def _session_id_for_position(position_id: str) -> str:
    return str(_awareness(position_id)["session_id"])


def _publish(event_type: NeuralEventType, position_id: str, payload: dict) -> None:
    with DatabaseConnectionFactory().connect() as conn:
        position = conn.execute("SELECT market_id FROM paper_positions WHERE id::text=%s", (position_id,)).fetchone()
    NeuralEventBusService().publish_event(
        event_type,
        source_component="Position Test",
        source_type="neuron",
        market_id=str(position["market_id"]),
        position_id=position_id,
        payload=payload,
    )


def test_position_awareness_created(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("created")

    result = PositionAwarenessService().refresh_position(position_id)

    assert result["status"] == "OK"
    awareness = _awareness(position_id)
    assert awareness["position_id"] == position_id
    assert awareness["session_id"].startswith("mesh_session_position_session_")


def test_pnl_rising_reaction(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("pnl-rise", unrealized="2.50")

    PositionAwarenessService().refresh_position(position_id)

    assert "PNL_RISING" in _reactions(position_id)


def test_pnl_falling_reaction(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("pnl-fall", unrealized="-1.10")

    PositionAwarenessService().refresh_position(position_id)

    assert "PNL_FALLING" in _reactions(position_id)


def test_adverse_news_reaction(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("news")
    PositionAwarenessService().refresh_position(position_id)

    _publish(NeuralEventType.NEWS_DETECTED, position_id, {"sentiment": "negative", "summary": "adverse news against position"})

    assert "ADVERSE_NEWS" in _reactions(position_id)


def test_whale_exit_reaction(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("whale")
    PositionAwarenessService().refresh_position(position_id)

    _publish(NeuralEventType.WHALE_DETECTED, position_id, {"action": "sell exit outflow"})

    assert "WHALE_EXIT" in _reactions(position_id)


def test_liquidity_drop_reaction(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("liquidity")
    PositionAwarenessService().refresh_position(position_id)

    _publish(NeuralEventType.LIQUIDITY_CHANGED, position_id, {"status": "drop thin deteriorated"})

    assert "LIQUIDITY_DROP" in _reactions(position_id)


def test_risk_increase_reaction(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("risk")
    PositionAwarenessService().refresh_position(position_id)

    _publish(NeuralEventType.RISK_CHANGED, position_id, {"risk": "increased high caution"})

    assert "RISK_INCREASED" in _reactions(position_id)


def test_capital_pressure_reaction(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("capital")
    PositionAwarenessService().refresh_position(position_id)
    SharedAwarenessService().refresh_session(_session_id_for_position(position_id))

    assert "CAPITAL_PRESSURE" in _reactions(position_id)


def test_position_aging_reaction(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("aging", opened_minutes_ago=900)

    PositionAwarenessService().refresh_position(position_id)

    assert "POSITION_AGING" in _reactions(position_id)


def test_coordinator_sees_position_awareness(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("coordinator")
    PositionAwarenessService().refresh_position(position_id)
    _publish(NeuralEventType.RISK_CHANGED, position_id, {"risk": "increased high caution"})
    session_id = _session_id_for_position(position_id)

    with DatabaseConnectionFactory().connect() as conn:
        opinion = conn.execute(
            """
            SELECT *
            FROM mesh_brain_opinions
            WHERE session_id=%s AND brain_type='POSITION_BRAIN'
            """,
            (session_id,),
        ).fetchone()
        decision = conn.execute(
            "SELECT * FROM mesh_coordinator_decisions WHERE session_id=%s",
            (session_id,),
        ).fetchone()

    assert opinion is not None
    assert "POSITION_AWARENESS" in opinion["consumed_domains_json"]
    assert decision is not None
    assert decision["final_action"] in {"WATCH", "EXIT_REVIEW", "HOLD_REVIEW"}


def test_dashboard_detail_and_source_links(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("dashboard")
    PositionAwarenessService().refresh_position(position_id)
    client = TestClient(create_app())

    summary = client.get("/dashboard/api/v2/positions-awareness")
    detail = client.get(f"/dashboard/api/v2/positions-awareness/{position_id}")

    assert summary.status_code == 200
    assert detail.status_code == 200
    assert summary.json()["mock_data"] is False
    assert detail.json()["mock_data"] is False
    assert detail.json()["sources"]
    assert detail.json()["awareness"]["position_id"] == position_id


def test_system_off_blocks_position_awareness_mutation(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("off")
    SystemPowerService().turn_off(actor="pytest", reason="position awareness off")

    with pytest.raises(PositionAwarenessBlocked):
        PositionAwarenessService().refresh_position(position_id)
    with pytest.raises(NeuralPublishBlocked):
        NeuralEventBusService().publish_event(
            NeuralEventType.PNL_CHANGED,
            source_component="Position Test",
            source_type="test",
            position_id=position_id,
            payload={"pnl": "falling"},
        )

    assert _count("position_awareness") == 0


def test_no_trading_mutation(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("safety")
    before = {
        "live_orders": _count("live_orders"),
        "paper_orders": _count("paper_orders"),
        "paper_fills": _count("paper_fills"),
        "paper_positions": _count("paper_positions"),
        "paper_intents": _count("paper_intents"),
        "orders_v2": _count("orders_v2"),
        "fills_v2": _count("fills_v2"),
        "positions": _count("positions"),
        "risk_decisions": _count("risk_decisions"),
        "exit_plans": _count("exit_plans"),
        "paper_eligibility_candidates": _count("paper_eligibility_candidates"),
        "coordinator_decisions": _count("coordinator_decisions"),
        "brain_outputs": _count("brain_outputs"),
    }

    PositionAwarenessService().refresh_position(position_id)
    SharedAwarenessService().refresh_session(_session_id_for_position(position_id))

    assert {table: _count(table) for table in before} == before


def test_runtime_publish_creates_position_awareness(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("runtime")
    PositionAwarenessService().refresh_position(position_id)

    _publish(NeuralEventType.PNL_CHANGED, position_id, {"pnl": "falling loss"})

    assert "PNL_FALLING" in _reactions(position_id)
    assert _awareness(position_id)["coordinator_status"] in {"UNKNOWN", "WATCH", "EXIT_REVIEW", "HOLD_REVIEW", "INSUFFICIENT_DATA"}


def test_brain_dialogue_materializes_position_awareness(postgres_test_schema) -> None:
    _prepare()
    position_id = _insert_position("dialogue")
    PositionAwarenessService().refresh_position(position_id)

    result = BrainDialogueService().materialize_recent(limit_per_source=100)
    feed = BrainDialogueService().list_events(limit=100, component="Position Awareness", component_type="position_awareness")

    assert result["status"] == "OK"
    assert any("Position Awareness:" in row["human_message"] for row in feed["events"])
