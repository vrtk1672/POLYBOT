from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.neural_bus.errors import NeuralPublishBlocked
from app.neural_bus.service import NeuralEventBusService
from app.neural_bus.types import NeuralEventType
from app.services.brain_dialogue import BrainDialogueService
from app.services.system_power import SystemPowerService
from app.shared_awareness.service import SharedAwarenessService


def _prepare() -> NeuralEventBusService:
    run_migrations()
    return NeuralEventBusService()


def _fetch_awareness(session_id: str) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM mesh_shared_awareness WHERE session_id = %s", (session_id,)).fetchone()
    assert row is not None
    return dict(row)


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
        return int(conn.execute("SELECT COUNT(*) AS count FROM " + table).fetchone()["count"] or 0)


def test_orderbook_event_creates_orderbook_awareness_and_missing_news(postgres_test_schema) -> None:
    service = _prepare()

    event = service.publish_event(
        NeuralEventType.ORDERBOOK_REFRESHED,
        source_component="Orderbook",
        source_type="neuron",
        market_id="awareness-orderbook-market",
        payload={"best_bid": 0.41, "best_ask": 0.43},
    )

    session = _session_for_event(event["event_id"], "MARKET_SESSION")
    awareness = _fetch_awareness(session["session_id"])
    assert awareness["orderbook_state_json"]["status"] == "PRESENT"
    assert awareness["orderbook_state_json"]["source_count"] == 1
    assert awareness["news_state_json"]["status"] == "MISSING"
    assert "NEWS" in awareness["missing_domains_json"]


def test_rules_evidence_creates_rules_awareness(postgres_test_schema) -> None:
    service = _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO rules_analysis (
                rules_analysis_id, market_id, rules_text_present, source_verification_status,
                recommendation, resolution_clarity, created_at
            )
            VALUES (%s, %s, true, 'VERIFIED', 'TRADE_ALLOWED', 0.8, now())
            """,
            ("rules-awareness-1", "awareness-rules-market"),
        )

    event = service.publish_event(
        NeuralEventType.MARKET_REPRICING,
        source_component="Market Neuron",
        source_type="market",
        market_id="awareness-rules-market",
        payload={"price": 0.52},
    )

    awareness = _fetch_awareness(_session_for_event(event["event_id"], "MARKET_SESSION")["session_id"])
    assert awareness["rules_state_json"]["status"] == "PRESENT"
    assert awareness["rules_state_json"]["source_refs"][0]["source_table"] == "rules_analysis"


def test_stale_orderbook_marks_orderbook_stale(postgres_test_schema) -> None:
    service = _prepare()
    old_at = datetime.now(UTC) - timedelta(hours=2)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask,
                spread, mid_price, snapshot_at, snapshot_status, is_stale, stale_reason
            )
            VALUES (%s, %s, 'token-stale', 'YES', 0.4, 0.45, 0.05, 0.425, %s, 'OK', true, 'TOO_OLD')
            """,
            ("stale-orderbook-1", "awareness-stale-market", old_at),
        )

    event = service.publish_event(
        NeuralEventType.MARKET_REPRICING,
        source_component="Market Neuron",
        source_type="market",
        market_id="awareness-stale-market",
        payload={"price": 0.42},
    )

    awareness = _fetch_awareness(_session_for_event(event["event_id"], "MARKET_SESSION")["session_id"])
    assert awareness["orderbook_state_json"]["status"] == "STALE"
    assert "ORDERBOOK" in awareness["stale_domains_json"]


def test_candidate_session_attaches_risk_and_exit_sources(postgres_test_schema) -> None:
    service = _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO risk_decisions (
                risk_decision_id, thesis_id, market_id, decision, risk_status,
                risk_score, confidence, created_at
            )
            VALUES ('risk-awareness-1', 'thesis-awareness-1', 'awareness-candidate-market', 'BLOCK', 'BLOCKED', 0.7, 0.8, now())
            """
        )
        conn.execute(
            """
            INSERT INTO exit_plans (
                exit_plan_id, market_id, plan_status, status, data_confidence, created_at, updated_at
            )
            VALUES ('exit-awareness-1', 'awareness-candidate-market', 'READY', 'COMPLETE', 0.75, now(), now())
            """
        )

    event = service.publish_event(
        NeuralEventType.ELIGIBILITY_CHANGED,
        source_component="Eligibility",
        source_type="eligibility",
        market_id="awareness-candidate-market",
        candidate_id="awareness-candidate-1",
        payload={"status": "BLOCKED"},
    )

    awareness = _fetch_awareness(_session_for_event(event["event_id"], "CANDIDATE_SESSION")["session_id"])
    assert awareness["risk_state_json"]["status"] in {"PRESENT", "PARTIAL"}
    assert awareness["exit_state_json"]["status"] in {"PRESENT", "PARTIAL"}
    assert {ref["source_table"] for ref in awareness["risk_state_json"]["source_refs"]} == {"risk_decisions"}
    assert {ref["source_table"] for ref in awareness["exit_state_json"]["source_refs"]} == {"exit_plans"}


def test_position_session_attaches_capital_and_pnl_sources(postgres_test_schema) -> None:
    service = _prepare()
    position_id = str(uuid4())
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_accounts (
                account_id, name, current_balance, available_balance, locked_balance, status, updated_at
            )
            VALUES ('paper-awareness', 'Paper Awareness', 1000, 900, 100, 'ACTIVE', now())
            """
        )
        conn.execute(
            """
            INSERT INTO paper_daily_pnl (pnl_date, realized_pnl, unrealized_pnl, net_pnl, updated_at)
            VALUES (%s, 1.25, 0.5, 1.75, now())
            """,
            (date.today(),),
        )

    event = service.publish_event(
        NeuralEventType.POSITION_OPENED,
        source_component="Position",
        source_type="paper",
        market_id="awareness-position-market",
        position_id=position_id,
        payload={"status": "OPEN"},
    )

    awareness = _fetch_awareness(_session_for_event(event["event_id"], "POSITION_SESSION")["session_id"])
    assert awareness["capital_state_json"]["status"] == "PRESENT"
    assert awareness["pnl_state_json"]["status"] == "PRESENT"


def test_awareness_source_refs_point_to_real_records_and_rebuild_is_idempotent(postgres_test_schema) -> None:
    service = _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, best_bid, best_ask,
                spread, mid_price, snapshot_at, snapshot_status, is_stale
            )
            VALUES ('real-orderbook-ref-1', 'awareness-real-ref-market', 'token-ref', 0.5, 0.51, 0.01, 0.505, now(), 'OK', false)
            """
        )
    event = service.publish_event(
        NeuralEventType.MARKET_REPRICING,
        source_component="Market Neuron",
        source_type="market",
        market_id="awareness-real-ref-market",
        payload={"price": 0.5},
    )
    session_id = _session_for_event(event["event_id"], "MARKET_SESSION")["session_id"]
    awareness = _fetch_awareness(session_id)
    source_count = _count("mesh_awareness_sources")

    SharedAwarenessService().refresh_session(session_id)

    assert _count("mesh_awareness_sources") == source_count
    with DatabaseConnectionFactory().connect() as conn:
        source = conn.execute(
            """
            SELECT *
            FROM mesh_awareness_sources
            WHERE awareness_id = %s AND source_table = 'orderbook_snapshots'
            LIMIT 1
            """,
            (awareness["awareness_id"],),
        ).fetchone()
        real = conn.execute(
            "SELECT * FROM orderbook_snapshots WHERE orderbook_snapshot_id = %s",
            (source["source_record_id"],),
        ).fetchone()
    assert source is not None
    assert real is not None


def test_shared_awareness_dashboard_summary_and_detail(postgres_test_schema) -> None:
    service = _prepare()
    event = service.publish_event(
        NeuralEventType.ORDERBOOK_REFRESHED,
        source_component="Orderbook",
        source_type="neuron",
        market_id="awareness-dashboard-market",
        payload={"snapshot_status": "OK"},
    )
    session_id = _session_for_event(event["event_id"], "MARKET_SESSION")["session_id"]
    client = TestClient(create_app())

    summary = client.get("/dashboard/api/v2/shared-awareness?limit=10")
    detail = client.get(f"/dashboard/api/v2/shared-awareness/{session_id}?limit=10")

    assert summary.status_code == 200
    assert detail.status_code == 200
    assert summary.json()["mock_data"] is False
    assert summary.json()["total_awareness_records"] >= 1
    assert detail.json()["mock_data"] is False
    assert detail.json()["domains"]["ORDERBOOK"]["status"] == "PRESENT"
    assert detail.json()["latest_linked_events"][0]["event_id"] == event["event_id"]


def test_system_off_blocks_awareness_mutation_from_runtime_publish(postgres_test_schema) -> None:
    service = _prepare()
    SystemPowerService().turn_off(actor="pytest", reason="shared awareness publish blocked")
    before = _count("mesh_shared_awareness")

    with pytest.raises(NeuralPublishBlocked):
        service.publish_event(
            NeuralEventType.ORDERBOOK_REFRESHED,
            source_component="Orderbook",
            source_type="neuron",
            market_id="awareness-blocked-market",
            payload={"snapshot": "blocked"},
        )

    assert _count("neural_events") == 0
    assert _count("mesh_sessions") == 0
    assert _count("mesh_shared_awareness") == before


def test_shared_awareness_does_not_mutate_trading_truth(postgres_test_schema) -> None:
    service = _prepare()
    before = {
        "live_orders": _count("live_orders"),
        "paper_orders": _count("paper_orders"),
        "paper_fills": _count("paper_fills"),
        "paper_positions": _count("paper_positions"),
        "orders_v2": _count("orders_v2"),
        "fills_v2": _count("fills_v2"),
        "positions": _count("positions"),
        "paper_accounts": _count("paper_accounts"),
    }

    service.publish_event(
        NeuralEventType.RISK_CHANGED,
        source_component="Risk",
        source_type="risk",
        market_id="awareness-safety-market",
        candidate_id="awareness-safety-candidate",
        payload={"decision": "BLOCK"},
    )

    after = {table: _count(table) for table in before}
    assert after == before


def test_brain_dialogue_materializes_shared_awareness_messages(postgres_test_schema) -> None:
    service = _prepare()
    service.publish_event(
        NeuralEventType.ORDERBOOK_REFRESHED,
        source_component="Orderbook",
        source_type="neuron",
        market_id="awareness-dialogue-market",
        payload={"snapshot_status": "OK"},
    )

    result = BrainDialogueService().materialize_recent(limit_per_source=50)
    feed = BrainDialogueService().list_events(limit=50, component="Shared Awareness")

    assert result["status"] == "OK"
    messages = [row["human_message"] for row in feed["events"]]
    assert any("Shared Awareness: Updated MARKET_SESSION awareness" in message for message in messages)
    assert any("NEWS" in message and "MISSING" in message for message in messages)
