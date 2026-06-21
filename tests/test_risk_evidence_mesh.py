from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import app
from app.services.lifecycle_governance import LifecycleGovernanceGateService
from app.services.risk_evidence_mesh import RiskEvidenceMeshService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "risk_evidence_mesh_sources",
            "risk_evidence_mesh_evaluations",
            "lifecycle_governance_sources",
            "lifecycle_governance_decisions",
            "trade_lifecycle_brain_contributions",
            "trade_lifecycle_plan_sources",
            "trade_lifecycle_plans",
            "capital_efficiency_sources",
            "capital_efficiency_evaluations",
            "payout_odds_sources",
            "payout_odds_evaluations",
            "risk_decisions",
            "orderbook_snapshots",
            "paper_intents",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "paper_position_closes",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def test_missing_trusted_orderbook_hard_blocks(postgres_test_schema) -> None:
    _prepare()
    plan_id = _seed_plan()

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)

    assert result["risk_decision"] == "RISK_BLOCK"
    assert result["risk_blocker_subtype"] == "RISK_BLOCKED_NO_TRUSTED_ORDERBOOK"


def test_stale_trusted_orderbook_hard_blocks(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook(collected_at=datetime.now(UTC) - timedelta(minutes=20))
    plan_id = _seed_plan(source_refs={"orderbook_snapshot_id": book_id})

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)

    assert result["risk_decision"] == "RISK_BLOCK"
    assert result["risk_blocker_subtype"] == "RISK_BLOCKED_STALE_CRITICAL_SOURCE"


def test_missing_executable_price_hard_blocks(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook(best_ask=None)
    plan_id = _seed_plan(source_refs={"orderbook_snapshot_id": book_id})

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)

    assert result["risk_decision"] == "RISK_BLOCK"
    assert result["risk_blocker_subtype"] == "RISK_BLOCKED_MISSING_EXECUTABLE_PRICE"


def test_spread_too_wide_hard_blocks(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook(spread=0.12)
    plan_id = _seed_plan(source_refs={"orderbook_snapshot_id": book_id})

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)

    assert result["risk_blocker_subtype"] == "RISK_BLOCKED_SPREAD"


def test_bad_liquidity_hard_blocks(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook(liquidity_score=0.05)
    plan_id = _seed_plan(source_refs={"orderbook_snapshot_id": book_id})

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)

    assert result["risk_blocker_subtype"] == "RISK_BLOCKED_BAD_LIQUIDITY"


def test_optional_whale_memory_and_fair_probability_do_not_hard_block(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook()
    payout_id = _seed_payout(risk_reward=2.0, fair_probability=None)
    cap_id = _seed_capital_efficiency(recommendation="CAPITAL_WATCH")
    plan_id = _seed_plan(source_refs={"orderbook_snapshot_id": book_id, "payout_odds_evaluation_id": payout_id, "capital_efficiency_evaluation_id": cap_id})

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)

    assert result["risk_decision"] in {"RISK_WATCH", "RISK_REVIEW", "RISK_SUPPORT"}
    assert "WHALE_CONTEXT_MISSING" in result["optional_missing"]
    assert "MEMORY_CONTEXT_MISSING" in result["optional_missing"]
    assert "FAIR_PROBABILITY_MISSING" in result["optional_missing"]
    assert result["blocking_evidence"] == []


def test_payout_liquidity_capital_setup_creates_review_without_fake_fair_probability(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook()
    payout_id = _seed_payout(risk_reward=4.0, fair_probability=None)
    cap_id = _seed_capital_efficiency(recommendation="CAPITAL_SUPPORT", score=0.7)
    plan_id = _seed_plan(source_refs={"orderbook_snapshot_id": book_id, "payout_odds_evaluation_id": payout_id, "capital_efficiency_evaluation_id": cap_id})

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)
        row = conn.execute("SELECT * FROM risk_evidence_mesh_evaluations WHERE evaluation_id=%s", (result["evaluation_id"],)).fetchone()

    assert result["risk_decision"] == "RISK_REVIEW"
    assert result["edge_source_type"] == "CAPITAL_EFFICIENCY_SETUP"
    assert row["metadata_json"]["no_fake_probability"] is True


def test_no_source_backed_edge_stays_blocked(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook()
    plan_id = _seed_plan(source_refs={"orderbook_snapshot_id": book_id})

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)

    assert result["risk_decision"] == "RISK_BLOCK"
    assert result["risk_blocker_subtype"] == "RISK_BLOCKED_NO_SOURCE_BACKED_EDGE"


def test_partial_lineage_becomes_review_when_critical_sources_exist(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook()
    risk_id = _seed_risk(blockers=["MISSING_SIGNAL_MARKET_BINDING"])
    payout_id = _seed_payout(risk_reward=2.0)
    plan_id = _seed_plan(source_refs={"orderbook_snapshot_id": book_id, "risk_decision_id": risk_id, "payout_odds_evaluation_id": payout_id})

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)

    assert result["risk_decision"] == "RISK_REVIEW"
    assert result["risk_blocker_subtype"] == "RISK_REVIEW_LINEAGE_PARTIAL"


def test_critical_lineage_missing_stays_blocked(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook()
    risk_id = _seed_risk(blockers=["MISSING_SIGNAL_MARKET_BINDING"])
    plan_id = _seed_plan(token_id=None, source_refs={"orderbook_snapshot_id": book_id, "risk_decision_id": risk_id})

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)

    assert result["risk_decision"] == "RISK_BLOCK"
    assert result["risk_blocker_subtype"] == "RISK_BLOCKED_LINEAGE_CRITICAL"


def test_lifecycle_governance_maps_risk_review_without_hard_risk_block(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook()
    payout_id = _seed_payout(risk_reward=2.0)
    plan_id = _seed_plan(risk_summary={"decision": "BLOCK", "risk_status": "BLOCKED", "blockers": ["THESIS_BLOCKED"]}, source_refs={"orderbook_snapshot_id": book_id, "payout_odds_evaluation_id": payout_id})
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)
        plan = dict(conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone())
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(conn, plan, request_action="OBSERVE")

    assert "RISK_BLOCKED" not in decision["critical_blockers_json"]
    assert decision["actionability_class"] != "HARD_BLOCK"
    assert decision["metadata_json"]["blocker_precision"]["risk_evidence"]["risk_decision"] == "RISK_REVIEW"


def test_dashboard_returns_mock_data_false(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook()
    plan_id = _seed_plan(source_refs={"orderbook_snapshot_id": book_id})
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        RiskEvidenceMeshService().evaluate_subject_with_conn(conn, subject_type="LIFECYCLE_PLAN", subject_id=plan_id)

    payload = TestClient(app).get("/dashboard/api/v2/risk-evidence-mesh").json()

    assert payload["mock_data"] is False
    assert payload["total_evaluations"] == 1


def test_evaluator_does_not_mutate_paper_or_live_artifacts(postgres_test_schema) -> None:
    _prepare()
    book_id = _seed_orderbook()
    plan_id = _seed_plan(source_refs={"orderbook_snapshot_id": book_id})
    before = _safety_counts()

    RiskEvidenceMeshService().evaluate_recent(limit=10)

    after = _safety_counts()
    assert before == after


def _seed_plan(
    *,
    market_id: str = "risk-mesh-market",
    side: str = "YES",
    token_id: str | None = "risk-mesh-token",
    condition_id: str = "risk-mesh-condition",
    risk_summary: dict[str, object] | None = None,
    source_refs: dict[str, object] | None = None,
) -> str:
    plan_id = f"risk-mesh-plan-{uuid4().hex}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO trade_lifecycle_plans (
                plan_id, subject_type, subject_id, market_id, condition_id, side, token_id, mesh_session_id,
                strategy_type, plan_status, decision_class, economic_thesis, entry_thesis, exit_thesis,
                hold_to_resolution_thesis, invalidation_rules_json, capital_plan_json, monitoring_plan_json,
                risk_summary_json, liquidity_summary_json, payout_summary_json, exit_hold_summary_json,
                capital_efficiency_summary_json, same_market_summary_json, coordinator_judgment_json,
                missing_inputs_json, source_refs_json, metadata_json, created_at, updated_at
            )
            VALUES (
                %s,'PAPER_CANDIDATE','candidate-risk-mesh',%s,%s,%s,%s,NULL,
                'WATCH_ONLY','PARTIAL','PAPER_CANDIDATE_REVIEW','economic','entry','exit','hold',
                '[]'::jsonb,'{}'::jsonb,'[]'::jsonb,%s::jsonb,'{}'::jsonb,'{}'::jsonb,'{}'::jsonb,
                '{}'::jsonb,'{"decision":"ALLOW"}'::jsonb,'{}'::jsonb,'[]'::jsonb,%s::jsonb,'{"test_fixture":true}'::jsonb,now(),now()
            )
            """,
            (plan_id, market_id, condition_id, side, token_id, Jsonb(risk_summary or {"decision": "APPROVE", "risk_status": "LOW"}), Jsonb(source_refs or {})),
        )
    return plan_id


def _seed_orderbook(*, best_ask: float | None = 0.4, spread: float = 0.03, liquidity_score: float = 0.8, collected_at: datetime | None = None) -> str:
    snapshot_id = f"risk-mesh-book-{uuid4().hex}"
    collected_at = collected_at or datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask, spread, mid_price,
                liquidity_score, source, snapshot_status, is_stale, snapshot_at, collected_at, created_at
            )
            VALUES (%s,'risk-mesh-market','risk-mesh-token','YES',0.37,%s,%s,0.385,%s,'test','OK',false,%s,%s,%s)
            """,
            (snapshot_id, best_ask, spread, liquidity_score, collected_at, collected_at, collected_at),
        )
    return snapshot_id


def _seed_payout(*, risk_reward: float, fair_probability: float | None = None) -> str:
    evaluation_id = f"risk-mesh-payout-{uuid4().hex}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO payout_odds_evaluations (
                evaluation_id, subject_type, subject_id, market_id, condition_id, side, token_id,
                price, price_source, stake_usd, quantity, shares_if_buy, payout_if_win,
                profit_if_win, max_loss, risk_reward, implied_probability, break_even_probability,
                fair_probability, expected_value, settlement_value_status, source_refs_json, metadata_json
            )
            VALUES (
                %s,'PAPER_CANDIDATE','risk-mesh-plan-source','risk-mesh-market','risk-mesh-condition','YES','risk-mesh-token',
                0.4,'test',100,250,250,250,150,100,%s,0.4,0.4,%s,NULL,'ENTRY_MODEL','{}'::jsonb,'{}'::jsonb
            )
            """,
            (evaluation_id, risk_reward, fair_probability),
        )
    return evaluation_id


def _seed_capital_efficiency(*, recommendation: str, score: float = 0.5) -> str:
    evaluation_id = f"risk-mesh-capital-{uuid4().hex}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO capital_efficiency_evaluations (
                evaluation_id, subject_type, subject_id, market_id, condition_id, side, token_id,
                capital_locked, potential_reward, risk_amount, reward_per_locked_dollar,
                capital_efficiency_score, recommendation, confidence, reason, missing_inputs_json, source_refs_json, metadata_json
            )
            VALUES (
                %s,'PAPER_CANDIDATE','risk-mesh-plan-source','risk-mesh-market','risk-mesh-condition','YES','risk-mesh-token',
                100,150,100,1.5,%s,%s,0.5,'test capital efficiency','[]'::jsonb,'{}'::jsonb,'{}'::jsonb
            )
            """,
            (evaluation_id, score, recommendation),
        )
    return evaluation_id


def _seed_risk(*, blockers: list[str]) -> str:
    risk_id = f"risk-mesh-risk-{uuid4().hex}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO risk_decisions (
                risk_decision_id, thesis_id, market_id, decision, risk_status, risk_score, confidence,
                max_position_size, max_loss, market_risk_score, liquidity_risk_score, spread_risk_score,
                missing_data_risk_score, confidence_risk_score, daily_exposure_risk_score,
                risk_reasons, blockers, warnings, required_missing_evidence, source_thesis_status,
                paper_candidate_allowed, execution_allowed, risk_approved
            )
            VALUES (
                %s,%s,'risk-mesh-market','BLOCK','BLOCKED',0.9,0.9,
                10,5,0.2,0.1,0.1,0.8,0,0,
                %s::jsonb,%s::jsonb,'[]'::jsonb,%s::jsonb,'BLOCKED',false,false,false
            )
            """,
            (risk_id, f"thesis-{uuid4().hex}", Jsonb(blockers), Jsonb(blockers), Jsonb(blockers)),
        )
    return risk_id


def _safety_counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {table: _count(conn, table) for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "paper_capital_ledger", "live_orders", "orders_v2", "fills_v2", "positions")}


def _count(conn, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])
