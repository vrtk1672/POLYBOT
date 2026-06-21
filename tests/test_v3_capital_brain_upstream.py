from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.capital_brain.service import CapitalBrainBlocked, CapitalBrainService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.multi_brain_consumption.service import MultiBrainConsumptionService
from app.neural_bus.errors import NeuralPublishBlocked
from app.neural_bus.service import NeuralEventBusService
from app.neural_bus.types import NeuralEventType
from app.services.brain_dialogue import BrainDialogueService
from app.services.system_power import SystemPowerService
from app.shared_awareness.types import ALL_DOMAINS, DOMAIN_STATE_COLUMNS, AwarenessDomain


def _prepare() -> None:
    run_migrations()


def _count(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
        if not exists:
            return 0
        return int(conn.execute("SELECT COUNT(*) AS count FROM " + table).fetchone()["count"] or 0)


def _evaluation(session_id: str) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            "SELECT * FROM capital_brain_evaluations WHERE session_id = %s",
            (session_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def _capital_opinion(session_id: str) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM mesh_brain_opinions
            WHERE session_id = %s AND brain_type = 'CAPITAL_BRAIN'
            """,
            (session_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def _set_account(
    *,
    available: str = "1000",
    locked: str = "0",
    current: str = "1000",
    exposure: str = "0",
    daily_pnl: str = "0",
    max_position_size: str = "25",
    max_open_positions: int = 3,
    max_total_open_exposure_pct: str = "15",
) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            UPDATE paper_accounts
            SET current_balance=%s,
                available_balance=%s,
                locked_balance=%s,
                open_exposure=%s,
                daily_pnl=%s,
                max_position_size=%s,
                max_open_positions=%s,
                max_total_open_exposure_pct=%s,
                updated_at=now()
            WHERE account_id='paper_default'
            """,
            (current, available, locked, exposure, daily_pnl, max_position_size, max_open_positions, max_total_open_exposure_pct),
        )


def _state(domain: AwarenessDomain, *, status: str = "PRESENT", summary: str | None = None, source_count: int = 1) -> dict:
    return {
        "status": status,
        "summary": summary or f"{domain.value} present",
        "confidence": 0.8 if status != "MISSING" else 0,
        "source_count": source_count,
        "latest_source_at": None,
        "source_refs": [] if status == "MISSING" else [{"source_table": "mesh_shared_awareness", "source_record_id": f"{domain.value.lower()}-source", "summary": summary or f"{domain.value} present"}],
    }


def _missing_state(domain: AwarenessDomain) -> dict:
    return _state(domain, status="MISSING", summary=f"{domain.value} missing", source_count=0)


def _insert_session_awareness(
    slug: str,
    *,
    session_type: str = "CANDIDATE_SESSION",
    required_capital: str | None = None,
    lock_minutes: int | None = None,
    fees_summary: str = "fees acceptable",
    liquidity_summary: str = "liquidity acceptable",
    position_summary: str | None = None,
    pnl_summary: str | None = None,
    risk_summary: str | None = None,
    exit_summary: str | None = None,
) -> str:
    session_id = f"capital-session-{slug}"
    market_id = f"capital-market-{slug}"
    candidate_id = None if session_type == "POSITION_SESSION" else f"capital-candidate-{slug}"
    position_id = str(uuid4()) if session_type == "POSITION_SESSION" else None
    states = {domain: _missing_state(domain) for domain in ALL_DOMAINS}
    for domain in (AwarenessDomain.CAPITAL, AwarenessDomain.FEES, AwarenessDomain.LIQUIDITY, AwarenessDomain.ORDERBOOK, AwarenessDomain.RISK):
        states[domain] = _state(domain)
    states[AwarenessDomain.FEES] = _state(AwarenessDomain.FEES, summary=fees_summary)
    states[AwarenessDomain.LIQUIDITY] = _state(AwarenessDomain.LIQUIDITY, summary=liquidity_summary)
    if position_summary:
        states[AwarenessDomain.POSITION] = _state(AwarenessDomain.POSITION, summary=position_summary)
    if pnl_summary:
        states[AwarenessDomain.PNL] = _state(AwarenessDomain.PNL, summary=pnl_summary)
    if risk_summary:
        states[AwarenessDomain.RISK] = _state(AwarenessDomain.RISK, summary=risk_summary)
    if exit_summary:
        states[AwarenessDomain.EXIT] = _state(AwarenessDomain.EXIT, summary=exit_summary)
    missing = [domain.value for domain, state in states.items() if state["status"] == "MISSING"]
    payload = {}
    if required_capital is not None:
        payload["estimated_required_capital"] = required_capital
    if lock_minutes is not None:
        payload["estimated_capital_lock_minutes"] = lock_minutes
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO mesh_sessions (
                session_id, session_type, market_id, candidate_id, position_id,
                title, status, opened_at, last_event_at, event_count, participant_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'ACTIVE', now(), now(), 1, 1, %s)
            """,
            (session_id, session_type, market_id, candidate_id, position_id, f"Capital test {slug}", Jsonb({"test": "v3.5"})),
        )
        conn.execute(
            """
            INSERT INTO mesh_shared_awareness (
                awareness_id, session_id, session_type, market_id, candidate_id, position_id,
                status, freshness_status, completeness_score, confidence_score,
                news_state_json, whale_state_json, social_state_json, rules_state_json,
                liquidity_state_json, orderbook_state_json, fees_state_json, time_state_json,
                risk_state_json, exit_state_json, capital_state_json, pnl_state_json,
                memory_state_json, position_state_json, candidate_state_json,
                missing_domains_json, stale_domains_json, source_counts_json, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'PARTIAL', 'FRESH', 0.5, 0.7,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '[]'::jsonb, %s, now())
            """,
            (
                f"awareness-{session_id}",
                session_id,
                session_type,
                market_id,
                candidate_id,
                position_id,
                *[Jsonb(states[domain]) for domain in ALL_DOMAINS],
                Jsonb(missing),
                Jsonb({domain.value: states[domain]["source_count"] for domain in ALL_DOMAINS}),
            ),
        )
        if payload:
            event_id = f"capital-event-{slug}"
            conn.execute(
                """
                INSERT INTO neural_events (
                    event_id, event_type, market_id, candidate_id, position_id,
                    source_component, source_type, payload_json, source_table, source_record_id
                )
                VALUES (%s, 'MARKET_REPRICING', %s, %s, %s, 'Capital Test', 'market', %s, 'neural_events', %s)
                """,
                (event_id, market_id, candidate_id, position_id, Jsonb(payload), event_id),
            )
            conn.execute(
                """
                INSERT INTO mesh_session_events (session_id, event_id, event_type, source_component, role, metadata_json)
                VALUES (%s, %s, 'MARKET_REPRICING', 'Capital Test', 'PRIMARY', '{}'::jsonb)
                """,
                (session_id, event_id),
            )
    return session_id


def test_capital_evaluation_created_for_candidate_session(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_session_awareness("created")

    result = CapitalBrainService().evaluate_session(session_id)

    assert result["status"] == "OK"
    assert _evaluation(session_id)["decision"] in {"CAPITAL_SUPPORT", "CAPITAL_WATCH"}


def test_available_balance_missing_returns_insufficient_data(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_session_awareness("missing-account")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM paper_accounts WHERE account_id='paper_default'")

    CapitalBrainService().evaluate_session(session_id)

    assert _evaluation(session_id)["decision"] == "CAPITAL_INSUFFICIENT_DATA"


def test_available_balance_zero_blocks(postgres_test_schema) -> None:
    _prepare()
    _set_account(available="0")
    session_id = _insert_session_awareness("zero")

    CapitalBrainService().evaluate_session(session_id)

    assert _evaluation(session_id)["decision"] == "CAPITAL_BLOCK"


def test_required_capital_gt_available_blocks(postgres_test_schema) -> None:
    _prepare()
    _set_account(available="10", max_position_size="100")
    session_id = _insert_session_awareness("required-gt-available", required_capital="20")

    CapitalBrainService().evaluate_session(session_id)

    assert _evaluation(session_id)["decision"] == "CAPITAL_BLOCK"
    assert "REQUIRED_GT_AVAILABLE" in _evaluation(session_id)["risk_flags_json"]


def test_max_position_size_exceeded_blocks(postgres_test_schema) -> None:
    _prepare()
    _set_account(available="100", max_position_size="15")
    session_id = _insert_session_awareness("max-size", required_capital="20")

    CapitalBrainService().evaluate_session(session_id)

    assert _evaluation(session_id)["decision"] == "CAPITAL_BLOCK"
    assert "MAX_POSITION_SIZE_EXCEEDED" in _evaluation(session_id)["risk_flags_json"]


def test_daily_loss_guard_blocks(postgres_test_schema) -> None:
    _prepare()
    _set_account(daily_pnl="-60")
    session_id = _insert_session_awareness("daily-loss")

    CapitalBrainService().evaluate_session(session_id)

    assert _evaluation(session_id)["decision"] == "CAPITAL_BLOCK"
    assert "DAILY_LOSS_GUARD" in _evaluation(session_id)["risk_flags_json"]


def test_max_open_positions_blocks(postgres_test_schema) -> None:
    _prepare()
    _set_account(max_open_positions=0)
    session_id = _insert_session_awareness("max-open")

    CapitalBrainService().evaluate_session(session_id)

    assert _evaluation(session_id)["decision"] == "CAPITAL_BLOCK"
    assert "MAX_OPEN_POSITIONS" in _evaluation(session_id)["risk_flags_json"]


def test_high_exposure_watches_or_blocks(postgres_test_schema) -> None:
    _prepare()
    _set_account(exposure="130", max_total_open_exposure_pct="15")
    session_id = _insert_session_awareness("high-exposure", required_capital="5")

    CapitalBrainService().evaluate_session(session_id)

    assert _evaluation(session_id)["decision"] in {"CAPITAL_WATCH", "CAPITAL_BLOCK"}
    assert set(_evaluation(session_id)["risk_flags_json"]) & {"HIGH_EXPOSURE", "MAX_EXPOSURE_LIMIT"}


def test_good_balance_acceptable_evidence_supports(postgres_test_schema) -> None:
    _prepare()
    _set_account(available="1000", exposure="0", max_position_size="25")
    session_id = _insert_session_awareness("support", required_capital="5")

    CapitalBrainService().evaluate_session(session_id)

    assert _evaluation(session_id)["decision"] == "CAPITAL_SUPPORT"


def test_long_lock_poor_fees_watches(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_session_awareness("long-fees", required_capital="5", lock_minutes=500, fees_summary="fees high and edge erased")

    CapitalBrainService().evaluate_session(session_id)

    assert _evaluation(session_id)["decision"] in {"CAPITAL_WATCH", "CAPITAL_BLOCK"}
    assert "LONG_LOCK_POOR_FEES" in _evaluation(session_id)["risk_flags_json"]


def test_profitable_adverse_position_recommends_release_review(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_session_awareness(
        "release",
        session_type="POSITION_SESSION",
        position_summary="position profitable",
        pnl_summary="profit positive",
        risk_summary="risk worsened adverse",
        exit_summary="exit_required",
    )

    CapitalBrainService().evaluate_session(session_id)

    assert _evaluation(session_id)["decision"] == "CAPITAL_RELEASE_REVIEW"


def test_healthy_position_watches(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_session_awareness("healthy-position", session_type="POSITION_SESSION", position_summary="position healthy")

    CapitalBrainService().evaluate_session(session_id)

    assert _evaluation(session_id)["decision"] == "CAPITAL_WATCH"


def test_source_links_dashboard_and_detail_return_truth(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_session_awareness("dashboard", required_capital="5")
    evaluation_id = CapitalBrainService().evaluate_session(session_id)["evaluation_id"]
    client = TestClient(create_app())

    summary = client.get("/dashboard/api/v2/capital-brain")
    detail = client.get(f"/dashboard/api/v2/capital-brain/{evaluation_id}")
    session_detail = client.get(f"/dashboard/api/v2/capital-brain/session/{session_id}")

    assert summary.status_code == 200
    assert detail.status_code == 200
    assert session_detail.status_code == 200
    assert summary.json()["mock_data"] is False
    assert detail.json()["sources"]
    assert session_detail.json()["evaluation"]["evaluation_id"] == evaluation_id


def test_system_off_blocks_capital_brain_mutation(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_session_awareness("off")
    SystemPowerService().turn_off(actor="pytest", reason="capital brain off")

    with pytest.raises(CapitalBrainBlocked):
        CapitalBrainService().evaluate_session(session_id)

    assert _count("capital_brain_evaluations") == 0
    with pytest.raises(NeuralPublishBlocked):
        NeuralEventBusService().publish_event(
            NeuralEventType.ORDERBOOK_REFRESHED,
            source_component="Orderbook",
            source_type="neuron",
            market_id="capital-off-market",
            payload={"estimated_required_capital": 5},
        )


def test_no_trading_or_capital_ledger_mutation(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_session_awareness("safety", required_capital="5")
    before = {
        "paper_capital_ledger": _count("paper_capital_ledger"),
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
    with DatabaseConnectionFactory().connect() as conn:
        balances_before = dict(conn.execute("SELECT current_balance, available_balance, locked_balance FROM paper_accounts WHERE account_id='paper_default'").fetchone())

    CapitalBrainService().evaluate_session(session_id)

    assert {table: _count(table) for table in before} == before
    with DatabaseConnectionFactory().connect() as conn:
        balances_after = dict(conn.execute("SELECT current_balance, available_balance, locked_balance FROM paper_accounts WHERE account_id='paper_default'").fetchone())
    assert balances_after == balances_before


def test_multi_brain_and_coordinator_consume_capital_evaluation(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_session_awareness("multi", required_capital="5")

    CapitalBrainService().evaluate_session(session_id)
    result = MultiBrainConsumptionService().consume_session(session_id)

    opinion = _capital_opinion(session_id)
    assert result["mesh_decision_id"]
    assert opinion["stance"] == "SUPPORT"
    assert "CAPITAL_BRAIN_EVALUATION" in opinion["consumed_domains_json"]
    with DatabaseConnectionFactory().connect() as conn:
        bundle = conn.execute("SELECT * FROM mesh_coordinator_input_bundles WHERE session_id=%s", (session_id,)).fetchone()
        decision = conn.execute("SELECT * FROM mesh_coordinator_decisions WHERE session_id=%s", (session_id,)).fetchone()
    assert bundle is not None and bundle["source_brain_count"] > 1
    assert decision is not None


def test_runtime_publish_creates_capital_evaluation_upstream(postgres_test_schema) -> None:
    _prepare()
    event = NeuralEventBusService().publish_event(
        NeuralEventType.ORDERBOOK_REFRESHED,
        source_component="Orderbook",
        source_type="neuron",
        market_id="capital-runtime-market",
        candidate_id="capital-runtime-candidate",
        payload={"estimated_required_capital": 5, "best_bid": 0.4, "best_ask": 0.41},
    )
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT e.*
            FROM capital_brain_evaluations e
            JOIN mesh_session_events se ON se.session_id = e.session_id
            WHERE se.event_id = %s
            LIMIT 1
            """,
            (event["event_id"],),
        ).fetchone()
    assert row is not None


def test_brain_dialogue_materializes_capital_evaluation(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_session_awareness("dialogue", required_capital="5")
    CapitalBrainService().evaluate_session(session_id)

    result = BrainDialogueService().materialize_recent(limit_per_source=100)
    feed = BrainDialogueService().list_events(limit=100, component="Capital Brain", component_type="capital_brain")

    assert result["status"] == "OK"
    assert any("Available=" in row["human_message"] for row in feed["events"])
