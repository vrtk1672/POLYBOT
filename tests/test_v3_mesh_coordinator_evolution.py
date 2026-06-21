from __future__ import annotations

from collections import Counter
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.mesh_coordinator.service import MeshCoordinatorBlocked, MeshCoordinatorDecisionService
from app.neural_bus.errors import NeuralPublishBlocked
from app.neural_bus.service import NeuralEventBusService
from app.neural_bus.types import NeuralEventType
from app.services.brain_dialogue import BrainDialogueService
from app.services.system_power import SystemPowerService


BRAIN_NAMES = {
    "RISK_BRAIN": "Risk Brain",
    "EXIT_BRAIN": "Exit Brain",
    "CAPITAL_BRAIN": "Capital Brain",
    "CONTEXT_BRAIN": "Context Brain",
    "POSITION_BRAIN": "Position Brain",
}


def _prepare() -> None:
    run_migrations()


def _count(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
        if not exists:
            return 0
        return int(conn.execute("SELECT COUNT(*) AS count FROM " + table).fetchone()["count"] or 0)


def _decision(session_id: str) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM mesh_coordinator_decisions
            WHERE session_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def _conflicts(decision_id: str) -> list[dict]:
    with DatabaseConnectionFactory().connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM mesh_conflict_records WHERE decision_id = %s ORDER BY id",
                (decision_id,),
            ).fetchall()
        ]


def _insert_mesh_case(
    slug: str,
    opinions: dict[str, str],
    *,
    session_type: str = "CANDIDATE_SESSION",
    position_id: str | None = None,
) -> str:
    market_id = f"mesh-coordinator-{slug}"
    candidate_id = f"candidate-{slug}" if session_type != "POSITION_SESSION" else None
    position_id = position_id or (f"position-{slug}" if session_type == "POSITION_SESSION" else None)
    session_id = f"session-{slug}"
    bundle_id = f"bundle-{slug}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO mesh_sessions (
                session_id, session_type, market_id, candidate_id, position_id,
                title, status, opened_at, last_event_at, event_count,
                participant_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'ACTIVE', now(), now(), 1, %s, %s)
            """,
            (
                session_id,
                session_type,
                market_id,
                candidate_id,
                position_id,
                f"Mesh coordinator test {slug}",
                len(opinions),
                Jsonb({"test": "v3.4"}),
            ),
        )
        for brain_type, stance in opinions.items():
            conn.execute(
                """
                INSERT INTO mesh_brain_opinions (
                    opinion_id, session_id, brain_name, brain_type, market_id,
                    candidate_id, position_id, stance, confidence, decision_bias,
                    reasoning_summary, consumed_domains_json, missing_domains_json,
                    stale_domains_json, supporting_sources_json, opposing_sources_json,
                    conflicts_json, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0.74, 'OBSERVE',
                        %s, %s, %s, %s, %s, %s, %s, now())
                """,
                (
                    f"opinion-{slug}-{brain_type.lower()}",
                    session_id,
                    BRAIN_NAMES[brain_type],
                    brain_type,
                    market_id,
                    candidate_id,
                    position_id,
                    stance,
                    f"{BRAIN_NAMES[brain_type]} produced {stance} from source-backed awareness.",
                    Jsonb(["RULES", "LIQUIDITY", "ORDERBOOK", "CAPITAL"]),
                    Jsonb([] if stance != "NO_SIGNAL" else ["NEWS"]),
                    Jsonb([]),
                    Jsonb([{"source": "mesh_shared_awareness", "session_id": session_id}]),
                    Jsonb([]),
                    Jsonb([]),
                ),
            )
        stance_counts = Counter(opinions.values())
        conn.execute(
            """
            INSERT INTO mesh_coordinator_input_bundles (
                bundle_id, session_id, market_id, candidate_id, position_id,
                source_brain_count, opinion_count, stance_summary_json,
                conflicts_detected, conflict_count, coordinator_ready, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, 0, true, now())
            """,
            (
                bundle_id,
                session_id,
                market_id,
                candidate_id,
                position_id,
                len(opinions),
                len(opinions),
                Jsonb(
                    {
                        "counts": dict(stance_counts),
                        "by_brain": [
                            {"brain_type": brain, "brain_name": BRAIN_NAMES[brain], "stance": stance, "confidence": 0.74}
                            for brain, stance in opinions.items()
                        ],
                        "conflicts": [],
                    }
                ),
            ),
        )
    return session_id


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
            VALUES (%s, 'V3.4 Test Account', 1000, %s, 1000 - %s, 'ACTIVE', now())
            """,
            (f"acct-{market_id}", capital_available, capital_available),
        )


def _session_for_event(event_id: str, session_type: str | None = None) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        params: list[object] = [event_id]
        where = "se.event_id = %s"
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
    return _session_for_event(event["event_id"], "MARKET_SESSION")["session_id"]


def test_coordinator_creates_decision_from_bundle_and_preserves_source_count(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "create",
        {"RISK_BRAIN": "CAUTION", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "SUPPORT", "CONTEXT_BRAIN": "NO_SIGNAL"},
    )

    result = MeshCoordinatorDecisionService().judge_session(session_id)
    decision = _decision(session_id)

    assert result["status"] == "OK"
    assert decision["source_brain_count"] == 4
    assert decision["opinion_count"] == 4
    assert decision["final_stance"] == "WATCH"
    assert decision["final_action"] == "WATCH"


def test_all_no_signal_resolves_to_insufficient_data(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "nosignal",
        {"RISK_BRAIN": "NO_SIGNAL", "CAPITAL_BRAIN": "NO_SIGNAL", "EXIT_BRAIN": "NO_SIGNAL", "CONTEXT_BRAIN": "NO_SIGNAL"},
    )

    MeshCoordinatorDecisionService().judge_session(session_id)

    decision = _decision(session_id)
    assert decision["final_stance"] == "INSUFFICIENT_DATA"
    assert decision["final_action"] == "INSUFFICIENT_DATA"


def test_risk_block_beats_context_support_and_records_conflict(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "riskblock",
        {"RISK_BRAIN": "BLOCK", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "SUPPORT", "CONTEXT_BRAIN": "SUPPORT"},
    )

    MeshCoordinatorDecisionService().judge_session(session_id)

    decision = _decision(session_id)
    conflicts = _conflicts(decision["decision_id"])
    assert decision["final_stance"] == "BLOCK"
    assert decision["final_action"] == "BLOCK"
    assert decision["conflicts_detected"] is True
    assert any(row["winner"] == "RISK_BRAIN" for row in conflicts)


def test_capital_block_beats_support(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "capitalblock",
        {"RISK_BRAIN": "SUPPORT", "CAPITAL_BRAIN": "BLOCK", "EXIT_BRAIN": "SUPPORT", "CONTEXT_BRAIN": "SUPPORT"},
    )

    MeshCoordinatorDecisionService().judge_session(session_id)

    decision = _decision(session_id)
    assert decision["final_stance"] == "BLOCK"
    assert decision["final_action"] == "BLOCK"
    assert any(item["brain_type"] == "CAPITAL_BRAIN" for item in decision["winning_brains_json"])


def test_exit_block_blocks_entry(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "exitblock",
        {"RISK_BRAIN": "SUPPORT", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "BLOCK", "CONTEXT_BRAIN": "SUPPORT"},
    )

    MeshCoordinatorDecisionService().judge_session(session_id)

    decision = _decision(session_id)
    assert decision["final_stance"] == "BLOCK"
    assert decision["final_action"] == "BLOCK"
    assert any(item["brain_type"] == "EXIT_BRAIN" for item in decision["winning_brains_json"])


def test_all_key_support_routes_to_paper_candidate_review_not_execution(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "allsupport",
        {"RISK_BRAIN": "SUPPORT", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "SUPPORT", "CONTEXT_BRAIN": "NO_SIGNAL"},
    )

    MeshCoordinatorDecisionService().judge_session(session_id)

    decision = _decision(session_id)
    assert decision["final_action"] == "PAPER_CANDIDATE_REVIEW"
    assert decision["final_action"] not in {"CREATE_ORDER", "EXECUTE", "OPEN_POSITION"}
    assert decision["safety_status"] == "SAFE_NON_EXECUTING"


def test_position_adverse_context_routes_to_exit_review(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "positionexit",
        {"RISK_BRAIN": "CAUTION", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "CAUTION", "POSITION_BRAIN": "SUPPORT"},
        session_type="POSITION_SESSION",
        position_id=f"pos-{uuid4()}",
    )

    MeshCoordinatorDecisionService().judge_session(session_id)

    decision = _decision(session_id)
    assert decision["final_stance"] == "EXIT_RECOMMENDED"
    assert decision["final_action"] == "EXIT_REVIEW"


def test_conflicts_recorded_and_no_conflict_when_opinions_align(postgres_test_schema) -> None:
    _prepare()
    conflict_session = _insert_mesh_case(
        "conflict",
        {"RISK_BRAIN": "BLOCK", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "SUPPORT", "CONTEXT_BRAIN": "SUPPORT"},
    )
    aligned_session = _insert_mesh_case(
        "aligned",
        {"RISK_BRAIN": "SUPPORT", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "SUPPORT", "CONTEXT_BRAIN": "SUPPORT"},
    )

    MeshCoordinatorDecisionService().judge_session(conflict_session)
    MeshCoordinatorDecisionService().judge_session(aligned_session)

    assert _decision(conflict_session)["conflict_count"] >= 1
    assert _conflicts(_decision(conflict_session)["decision_id"])
    assert _decision(aligned_session)["conflict_count"] == 0
    assert _conflicts(_decision(aligned_session)["decision_id"]) == []


def test_source_links_point_to_real_opinions_and_rerun_is_idempotent(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "sources",
        {"RISK_BRAIN": "CAUTION", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "SUPPORT", "CONTEXT_BRAIN": "NO_SIGNAL"},
    )
    service = MeshCoordinatorDecisionService()

    service.judge_session(session_id)
    before_decisions = _count("mesh_coordinator_decisions")
    before_sources = _count("mesh_coordinator_decision_sources")
    before_conflicts = _count("mesh_conflict_records")
    service.judge_session(session_id)

    assert _count("mesh_coordinator_decisions") == before_decisions
    assert _count("mesh_coordinator_decision_sources") == before_sources
    assert _count("mesh_conflict_records") == before_conflicts
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT s.*
            FROM mesh_coordinator_decision_sources s
            JOIN mesh_brain_opinions o ON o.opinion_id = s.opinion_id
            WHERE o.session_id = %s
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    assert row is not None


def test_dashboard_summary_detail_and_session_routes_return_truth(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "dashboard",
        {"RISK_BRAIN": "SUPPORT", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "SUPPORT", "CONTEXT_BRAIN": "NO_SIGNAL"},
    )
    decision_id = MeshCoordinatorDecisionService().judge_session(session_id)["decision_id"]
    client = TestClient(create_app())

    summary = client.get("/dashboard/api/v2/mesh-coordinator?limit=10")
    detail = client.get(f"/dashboard/api/v2/mesh-coordinator/{decision_id}")
    session_detail = client.get(f"/dashboard/api/v2/mesh-coordinator/session/{session_id}")

    assert summary.status_code == 200
    assert detail.status_code == 200
    assert session_detail.status_code == 200
    assert summary.json()["mock_data"] is False
    assert summary.json()["total_mesh_decisions"] >= 1
    assert detail.json()["mock_data"] is False
    assert detail.json()["source_refs"]
    assert session_detail.json()["decision"]["decision_id"] == decision_id


def test_system_off_blocks_mesh_coordinator_mutation_from_runtime_publish(postgres_test_schema) -> None:
    _prepare()
    service = NeuralEventBusService()
    SystemPowerService().turn_off(actor="pytest", reason="mesh coordinator publish blocked")
    before = _count("mesh_coordinator_decisions")

    with pytest.raises(NeuralPublishBlocked):
        service.publish_event(
            NeuralEventType.ORDERBOOK_REFRESHED,
            source_component="Orderbook",
            source_type="neuron",
            market_id="mesh-coordinator-blocked-market",
            payload={"snapshot": "blocked"},
        )

    assert _count("neural_events") == 0
    assert _count("mesh_sessions") == 0
    assert _count("mesh_shared_awareness") == 0
    assert _count("mesh_brain_opinions") == 0
    assert _count("mesh_coordinator_decisions") == before


def test_system_off_blocks_direct_coordinator_judgment(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "offdirect",
        {"RISK_BRAIN": "SUPPORT", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "SUPPORT", "CONTEXT_BRAIN": "NO_SIGNAL"},
    )
    SystemPowerService().turn_off(actor="pytest", reason="mesh coordinator direct blocked")

    with pytest.raises(MeshCoordinatorBlocked):
        MeshCoordinatorDecisionService().judge_session(session_id)

    assert _count("mesh_coordinator_decisions") == 0


def test_runtime_publish_creates_mesh_coordinator_decision(postgres_test_schema) -> None:
    _prepare()
    service = NeuralEventBusService()
    market_id = "mesh-coordinator-runtime-market"
    _seed_market_context(market_id)

    session_id = _publish_rich_market(service, market_id)

    decision = _decision(session_id)
    assert decision["source_brain_count"] > 1
    assert decision["final_action"] in {"WATCH", "PAPER_CANDIDATE_REVIEW", "INSUFFICIENT_DATA", "BLOCK"}


def test_mesh_coordinator_does_not_mutate_trading_or_legacy_decision_truth(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "safety",
        {"RISK_BRAIN": "SUPPORT", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "SUPPORT", "CONTEXT_BRAIN": "NO_SIGNAL"},
    )
    before = {
        "live_orders": _count("live_orders"),
        "paper_orders": _count("paper_orders"),
        "paper_fills": _count("paper_fills"),
        "paper_positions": _count("paper_positions"),
        "paper_intents": _count("paper_intents"),
        "orders_v2": _count("orders_v2"),
        "fills_v2": _count("fills_v2"),
        "positions": _count("positions"),
        "paper_accounts": _count("paper_accounts"),
        "risk_decisions": _count("risk_decisions"),
        "exit_plans": _count("exit_plans"),
        "paper_eligibility_candidates": _count("paper_eligibility_candidates"),
        "coordinator_decisions": _count("coordinator_decisions"),
        "brain_outputs": _count("brain_outputs"),
    }

    MeshCoordinatorDecisionService().judge_session(session_id)

    assert {table: _count(table) for table in before} == before


def test_brain_dialogue_materializes_mesh_coordinator_decisions(postgres_test_schema) -> None:
    _prepare()
    session_id = _insert_mesh_case(
        "dialogue",
        {"RISK_BRAIN": "BLOCK", "CAPITAL_BRAIN": "SUPPORT", "EXIT_BRAIN": "SUPPORT", "CONTEXT_BRAIN": "SUPPORT"},
    )
    MeshCoordinatorDecisionService().judge_session(session_id)

    result = BrainDialogueService().materialize_recent(limit_per_source=100)
    decision_feed = BrainDialogueService().list_events(limit=100, component="Coordinator", component_type="mesh_coordinator")

    assert result["status"] == "OK"
    messages = [row["human_message"] for row in decision_feed["events"]]
    assert any("Final mesh decision" in message for message in messages)
    assert any("Conflict detected" in message for message in messages)
