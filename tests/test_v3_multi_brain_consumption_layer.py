from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.multi_brain_consumption.service import MultiBrainConsumptionService
from app.neural_bus.errors import NeuralPublishBlocked
from app.neural_bus.service import NeuralEventBusService
from app.neural_bus.types import NeuralEventType
from app.services.brain_dialogue import BrainDialogueService
from app.services.system_power import SystemPowerService


def _prepare() -> NeuralEventBusService:
    run_migrations()
    return NeuralEventBusService()


def _count(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
        if not exists:
            return 0
        return int(conn.execute("SELECT COUNT(*) AS count FROM " + table).fetchone()["count"] or 0)


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


def _opinions(session_id: str) -> list[dict]:
    with DatabaseConnectionFactory().connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_brain_opinions
                WHERE session_id = %s
                ORDER BY brain_type
                """,
                (session_id,),
            ).fetchall()
        ]


def _opinion(session_id: str, brain_type: str) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM mesh_brain_opinions
            WHERE session_id = %s AND brain_type = %s
            """,
            (session_id, brain_type),
        ).fetchone()
    assert row is not None
    return dict(row)


def _bundle(session_id: str) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            "SELECT * FROM mesh_coordinator_input_bundles WHERE session_id = %s",
            (session_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def _seed_market_context(market_id: str, *, capital_available: int = 900) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO rules_analysis (
                rules_analysis_id, market_id, rules_text_present, source_verification_status,
                recommendation, resolution_clarity, created_at
            )
            VALUES (%s, %s, true, 'VERIFIED', 'TRADE_ALLOWED', 0.85, now())
            """,
            (f"rules-{market_id}", market_id),
        )
        conn.execute(
            """
            INSERT INTO fee_snapshots (
                fee_snapshot_id, market_id, maker_fee, taker_fee, spread_cost, net_edge_adjustment, snapshot_at
            )
            VALUES (%s, %s, 0.01, 0.02, 0.01, 0.03, now())
            """,
            (f"fees-{market_id}", market_id),
        )
        conn.execute(
            """
            INSERT INTO paper_accounts (
                account_id, name, current_balance, available_balance, locked_balance, status, updated_at
            )
            VALUES (%s, 'V3.3 Test Account', 1000, %s, 1000 - %s, 'ACTIVE', now())
            """,
            (f"acct-{market_id}", capital_available, capital_available),
        )


def _publish_rich_market(service: NeuralEventBusService, market_id: str) -> str:
    event = service.publish_event(
        NeuralEventType.ORDERBOOK_REFRESHED,
        source_component="Orderbook",
        source_type="neuron",
        market_id=market_id,
        payload={"best_bid": 0.45, "best_ask": 0.46},
    )
    service.publish_event(
        NeuralEventType.LIQUIDITY_CHANGED,
        source_component="Liquidity",
        source_type="neuron",
        market_id=market_id,
        payload={"liquidity": 1200},
    )
    service.publish_event(
        NeuralEventType.MARKET_REPRICING,
        source_component="Market Neuron",
        source_type="market",
        market_id=market_id,
        payload={"price": 0.455},
    )
    return _session_for_event(event["event_id"], "MARKET_SESSION")["session_id"]


def test_shared_awareness_session_creates_multiple_brain_opinions(postgres_test_schema) -> None:
    service = _prepare()
    _seed_market_context("multi-brain-rich-market")

    session_id = _publish_rich_market(service, "multi-brain-rich-market")
    opinions = _opinions(session_id)

    brain_types = {row["brain_type"] for row in opinions}
    assert {"RISK_BRAIN", "EXIT_BRAIN", "CAPITAL_BRAIN", "CONTEXT_BRAIN", "COORDINATOR_OBSERVER"}.issubset(brain_types)
    assert _bundle(session_id)["source_brain_count"] > 1


def test_risk_brain_consumes_rules_liquidity_fees_and_capital(postgres_test_schema) -> None:
    service = _prepare()
    _seed_market_context("multi-brain-risk-market")

    session_id = _publish_rich_market(service, "multi-brain-risk-market")
    risk = _opinion(session_id, "RISK_BRAIN")

    assert {"RULES", "LIQUIDITY", "ORDERBOOK", "FEES", "CAPITAL"}.issubset(set(risk["consumed_domains_json"]))
    assert risk["stance"] in {"SUPPORT", "CAUTION"}


def test_exit_brain_consumes_risk_liquidity_time_and_position_when_available(postgres_test_schema) -> None:
    service = _prepare()
    market_id = "multi-brain-exit-position-market"
    position_id = str(uuid4())
    _seed_market_context(market_id)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO risk_decisions (risk_decision_id, thesis_id, market_id, decision, risk_status, risk_score, confidence, created_at)
            VALUES ('risk-exit-v33', 'thesis-exit-v33', %s, 'APPROVE', 'LOW', 0.2, 0.8, now())
            """,
            (market_id,),
        )
        conn.execute(
            """
            INSERT INTO paper_daily_pnl (pnl_date, realized_pnl, unrealized_pnl, net_pnl, updated_at)
            VALUES (%s, 1, 2, 3, now())
            """,
            (date.today(),),
        )

    event = service.publish_event(
        NeuralEventType.POSITION_OPENED,
        source_component="Position",
        source_type="paper",
        market_id=market_id,
        position_id=position_id,
        payload={"status": "OPEN"},
    )
    service.publish_event(
        NeuralEventType.LIQUIDITY_CHANGED,
        source_component="Liquidity",
        source_type="neuron",
        market_id=market_id,
        position_id=position_id,
        payload={"liquidity": 1000},
    )
    service.publish_event(
        NeuralEventType.MARKET_REPRICING,
        source_component="Market Neuron",
        source_type="market",
        market_id=market_id,
        position_id=position_id,
        payload={"price": 0.5},
    )
    session_id = _session_for_event(event["event_id"], "POSITION_SESSION")["session_id"]
    exit_opinion = _opinion(session_id, "EXIT_BRAIN")

    assert {"RISK", "LIQUIDITY", "TIME", "POSITION", "PNL"}.issubset(set(exit_opinion["consumed_domains_json"]))
    assert "POSITION_BRAIN" in {row["brain_type"] for row in _opinions(session_id)}


def test_capital_brain_consumes_capital_time_fees_and_pnl(postgres_test_schema) -> None:
    service = _prepare()
    market_id = "multi-brain-capital-market"
    position_id = str(uuid4())
    _seed_market_context(market_id)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_daily_pnl (pnl_date, realized_pnl, unrealized_pnl, net_pnl, updated_at)
            VALUES (%s, 2, 3, 5, now())
            """,
            (date.today(),),
        )
    event = service.publish_event(
        NeuralEventType.POSITION_OPENED,
        source_component="Position",
        source_type="paper",
        market_id=market_id,
        position_id=position_id,
        payload={"status": "OPEN"},
    )
    service.publish_event(
        NeuralEventType.MARKET_REPRICING,
        source_component="Market Neuron",
        source_type="market",
        market_id=market_id,
        position_id=position_id,
        payload={"price": 0.5},
    )
    session_id = _session_for_event(event["event_id"], "POSITION_SESSION")["session_id"]

    capital = _opinion(session_id, "CAPITAL_BRAIN")
    assert {"CAPITAL", "FEES", "TIME", "PNL"}.issubset(set(capital["consumed_domains_json"]))


def test_context_brain_marks_missing_news_whale_social_honestly(postgres_test_schema) -> None:
    service = _prepare()
    _seed_market_context("multi-brain-context-market")

    session_id = _publish_rich_market(service, "multi-brain-context-market")
    context = _opinion(session_id, "CONTEXT_BRAIN")

    assert {"NEWS", "WHALE", "SOCIAL"}.issubset(set(context["missing_domains_json"]))
    assert context["stance"] in {"SUPPORT", "NO_SIGNAL"}


def test_position_brain_only_runs_when_position_context_exists(postgres_test_schema) -> None:
    service = _prepare()
    _seed_market_context("multi-brain-no-position-market")
    market_session_id = _publish_rich_market(service, "multi-brain-no-position-market")

    assert "POSITION_BRAIN" not in {row["brain_type"] for row in _opinions(market_session_id)}

    position_event = service.publish_event(
        NeuralEventType.POSITION_OPENED,
        source_component="Position",
        source_type="paper",
        market_id="multi-brain-no-position-market",
        position_id=str(uuid4()),
        payload={"status": "OPEN"},
    )
    position_session_id = _session_for_event(position_event["event_id"], "POSITION_SESSION")["session_id"]
    assert "POSITION_BRAIN" in {row["brain_type"] for row in _opinions(position_session_id)}


def test_coordinator_bundle_records_source_brain_count_gt_one_and_conflicts(postgres_test_schema) -> None:
    service = _prepare()
    _seed_market_context("multi-brain-conflict-market", capital_available=0)

    session_id = _publish_rich_market(service, "multi-brain-conflict-market")
    bundle = _bundle(session_id)

    assert bundle["source_brain_count"] > 1
    assert bundle["conflicts_detected"] is True
    assert bundle["conflict_count"] >= 1
    assert any(item["left_stance"] == "SUPPORT" and item["right_stance"] == "BLOCK" for item in bundle["stance_summary_json"]["conflicts"])


def test_no_conflict_when_opinions_align_without_block(postgres_test_schema) -> None:
    service = _prepare()
    _seed_market_context("multi-brain-align-market", capital_available=900)

    session_id = _publish_rich_market(service, "multi-brain-align-market")
    bundle = _bundle(session_id)

    assert bundle["source_brain_count"] > 1
    assert bundle["conflicts_detected"] is False
    assert bundle["conflict_count"] == 0


def test_source_links_point_to_real_awareness_sources_and_idempotent(postgres_test_schema) -> None:
    service = _prepare()
    _seed_market_context("multi-brain-source-market")
    session_id = _publish_rich_market(service, "multi-brain-source-market")
    before_opinions = _count("mesh_brain_opinions")
    before_sources = _count("mesh_brain_consumption_sources")

    MultiBrainConsumptionService().consume_session(session_id)

    assert _count("mesh_brain_opinions") == before_opinions
    assert _count("mesh_brain_consumption_sources") == before_sources
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT mbs.*
            FROM mesh_brain_consumption_sources mbs
            JOIN mesh_awareness_sources mas
              ON mas.session_id = mbs.session_id
             AND mas.source_domain = mbs.source_domain
             AND mas.source_table = mbs.source_table
             AND mas.source_record_id = mbs.source_record_id
            WHERE mbs.session_id = %s
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    assert row is not None


def test_dashboard_summary_and_detail_return_truth(postgres_test_schema) -> None:
    service = _prepare()
    _seed_market_context("multi-brain-dashboard-market")
    session_id = _publish_rich_market(service, "multi-brain-dashboard-market")
    client = TestClient(create_app())

    summary = client.get("/dashboard/api/v2/multi-brain-consumption?limit=10")
    detail = client.get(f"/dashboard/api/v2/multi-brain-consumption/{session_id}?limit=10")

    assert summary.status_code == 200
    assert detail.status_code == 200
    assert summary.json()["mock_data"] is False
    assert summary.json()["total_brain_opinions"] >= 4
    assert detail.json()["mock_data"] is False
    assert detail.json()["coordinator_input_bundle"]["source_brain_count"] > 1
    assert detail.json()["brain_opinions"]


def test_system_off_blocks_multi_brain_mutation_from_runtime_publish(postgres_test_schema) -> None:
    service = _prepare()
    SystemPowerService().turn_off(actor="pytest", reason="multi-brain publish blocked")
    before = _count("mesh_brain_opinions")

    with pytest.raises(NeuralPublishBlocked):
        service.publish_event(
            NeuralEventType.ORDERBOOK_REFRESHED,
            source_component="Orderbook",
            source_type="neuron",
            market_id="multi-brain-blocked-market",
            payload={"snapshot": "blocked"},
        )

    assert _count("neural_events") == 0
    assert _count("mesh_sessions") == 0
    assert _count("mesh_shared_awareness") == 0
    assert _count("mesh_brain_opinions") == before


def test_multi_brain_consumption_does_not_mutate_trading_or_decision_truth(postgres_test_schema) -> None:
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
        "risk_decisions": _count("risk_decisions"),
        "exit_plans": _count("exit_plans"),
        "paper_eligibility_candidates": _count("paper_eligibility_candidates"),
        "paper_intents": _count("paper_intents"),
        "coordinator_decisions": _count("coordinator_decisions"),
        "brain_outputs": _count("brain_outputs"),
    }

    _seed_market_context("multi-brain-safety-market")
    _publish_rich_market(service, "multi-brain-safety-market")

    after = {table: _count(table) for table in before}
    assert after["paper_accounts"] == before["paper_accounts"] + 1
    after["paper_accounts"] = before["paper_accounts"]
    assert after == before


def test_brain_dialogue_materializes_multi_brain_opinions(postgres_test_schema) -> None:
    service = _prepare()
    _seed_market_context("multi-brain-dialogue-market", capital_available=0)
    _publish_rich_market(service, "multi-brain-dialogue-market")

    result = BrainDialogueService().materialize_recent(limit_per_source=100)
    feed = BrainDialogueService().list_events(limit=100, component_type="brain_opinion")
    coordinator_feed = BrainDialogueService().list_events(limit=100, component="Coordinator Observer")

    assert result["status"] == "OK"
    messages = [row["human_message"] for row in feed["events"]]
    assert any("Risk Brain: Consumed" in message for message in messages)
    assert any("Capital Brain: Consumed" in message for message in messages)
    assert any("Conflict detected" in row["human_message"] for row in coordinator_feed["events"])
