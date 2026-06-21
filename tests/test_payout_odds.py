from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.capital_brain.service import CapitalBrainService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import app
from app.mesh_coordinator.service import MeshCoordinatorDecisionService
from app.services.exit_foundation import ExitFoundationService
from app.services.paper_trade_forensics import PaperTradeForensicsService
from app.services.payout_odds import PayoutOddsService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "brain_dialogue_events",
            "payout_odds_sources",
            "payout_odds_evaluations",
            "paper_position_closes",
            "paper_capital_ledger",
            "paper_trade_ledger",
            "paper_fills",
            "paper_positions",
            "paper_orders",
            "paper_runs",
            "paper_intents",
            "paper_eligibility_candidates",
            "fresh_candidate_seeds",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def test_candidate_price_080_computes_implied_probability(postgres_test_schema) -> None:
    _prepare()

    math = PayoutOddsService().compute_candidate_math(price=Decimal("0.80"), stake_usd=Decimal("100"))

    assert math.implied_probability == Decimal("0.80")
    assert math.break_even_probability == Decimal("0.80")


def test_stake_100_at_080_computes_shares_payout_profit_loss(postgres_test_schema) -> None:
    _prepare()

    math = PayoutOddsService().compute_candidate_math(price=Decimal("0.80"), stake_usd=Decimal("100"))

    assert math.shares_if_buy == Decimal("125")
    assert math.payout_if_win == Decimal("125")
    assert math.profit_if_win == Decimal("25")
    assert math.max_loss == Decimal("100")


def test_stake_100_at_020_computes_high_reward(postgres_test_schema) -> None:
    _prepare()

    math = PayoutOddsService().compute_candidate_math(price=Decimal("0.20"), stake_usd=Decimal("100"))

    assert math.shares_if_buy == Decimal("500")
    assert math.payout_if_win == Decimal("500")
    assert math.profit_if_win == Decimal("400")
    assert math.risk_reward == Decimal("4")


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("1"), Decimal("1.20")])
def test_invalid_price_rejected(postgres_test_schema, price: Decimal) -> None:
    _prepare()

    with pytest.raises(ValueError):
        PayoutOddsService().compute_candidate_math(price=price, stake_usd=Decimal("100"))


def test_missing_executable_price_records_missing_price(postgres_test_schema) -> None:
    _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO fresh_candidate_seeds (
                seed_id, market_id, condition_id, side, expected_token_id, yes_token_id, no_token_id, source,
                status, created_at, updated_at, metadata_json
            )
            VALUES (
                'seed-missing-price', 'market-missing-price', 'condition-x', 'YES', 'token-yes', 'token-yes', 'token-no', 'test',
                'BOOK_VERIFIED', now(), now(), '{}'::jsonb
            )
            """
        )

    result = PayoutOddsService().evaluate_recent(subject_type="FRESH_SEED", limit=10)

    assert result["outcomes_by_status"]["MISSING_PRICE"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM payout_odds_evaluations WHERE subject_id='seed-missing-price'").fetchone()
        assert row["settlement_value_status"] == "MISSING_PRICE"


def test_position_entry_price_quantity_computes_resolution_value(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="5")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = PayoutOddsService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    assert result["status"] == "OK"
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM payout_odds_evaluations WHERE subject_id=%s", (position_id,)).fetchone()
        assert row["stake_usd"] == Decimal("1.000000")
        assert row["payout_if_win"] == Decimal("5.000000")
        assert row["profit_if_win"] == Decimal("4.000000")
        assert row["expected_value"] is None
        assert row["fair_probability"] is None


def test_source_refs_preserved_for_intent_evaluation(postgres_test_schema) -> None:
    _prepare()
    intent_id = _seed_intent(price="0.25", notional="5", quantity="10")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = PayoutOddsService().evaluate_subject_with_conn(conn, subject_type="PAPER_INTENT", subject_id=intent_id)

    assert result["status"] == "OK"
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM payout_odds_evaluations WHERE subject_id=%s", (intent_id,)).fetchone()
        source = conn.execute("SELECT * FROM payout_odds_sources WHERE evaluation_id=%s", (row["evaluation_id"],)).fetchone()
        assert row["source_refs_json"]["source_table"] == "paper_intents"
        assert source["source_table"] == "paper_intents"
        assert row["expected_value"] is None


def test_dashboard_returns_mock_data_false(postgres_test_schema) -> None:
    _prepare()
    _seed_intent(price="0.20", notional="5", quantity="10")
    PayoutOddsService().evaluate_recent(subject_type="PAPER_INTENT", limit=10)

    response = TestClient(app).get("/dashboard/api/v2/payout-odds")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["total_evaluations"] >= 1
    assert payload["avg_risk_reward"] > 0


def test_paper_forensics_includes_payout_odds_fields(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="5")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        PayoutOddsService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    trace = PaperTradeForensicsService().get_trade(position_id)

    assert trace["mock_data"] is False
    assert trace["payout_if_win"] == 5.0
    assert trace["profit_if_win"] == 4.0
    assert trace["implied_probability_at_entry"] == 0.2
    assert trace["missing_payout_fields"] == []


def test_capital_exit_coordinator_visibility_observational_only(postgres_test_schema) -> None:
    _prepare()
    _seed_intent(price="0.20", notional="5", quantity="10")
    PayoutOddsService().evaluate_recent(subject_type="PAPER_INTENT", limit=10)

    capital = CapitalBrainService().dashboard_summary(limit=5)
    exit_payload = ExitFoundationService().get_dashboard_summary(limit=5)
    coordinator = MeshCoordinatorDecisionService().dashboard_summary(limit=5)

    assert capital["payout_odds_observational_only"] is True
    assert exit_payload["payout_odds_observational_only"] is True
    assert coordinator["payout_odds_observational_only"] is True


def test_evaluator_does_not_mutate_trading_or_capital_tables(postgres_test_schema) -> None:
    _prepare()
    _seed_intent(price="0.20", notional="5", quantity="10")
    with DatabaseConnectionFactory().connect() as conn:
        before = _safety_counts(conn)

    result = PayoutOddsService().evaluate_recent(limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        after = _safety_counts(conn)
    assert result["trading_mutation"] is False
    assert before == after


def _seed_intent(*, price: str, notional: str, quantity: str) -> str:
    intent_id = f"intent-{uuid4().hex}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                coordinator_decision_id, market_id, side, price_basis, intended_price,
                max_slippage, confidence, intent_status, intent_type, intent_reason, evidence,
                blockers, paper_only, live, execution_allowed, order_intent_created,
                generated_by, producer_name, is_runtime_generated, is_dry_run_generated,
                created_at, updated_at
            )
            VALUES (
                %s, %s, 'thesis-test', 'risk-test', 'exit-test',
                'coord-test', 'payout-market', 'YES', 'ORDERBOOK_BEST_ASK', %s,
                0, 0.9, 'CREATED', 'PAPER_ENTRY_INTENT', 'test', %s,
                '[]'::jsonb, true, false, false, false,
                'test', 'test', true, false,
                now(), now()
            )
            """,
            (
                intent_id,
                f"eligibility-{intent_id}",
                Decimal(price),
                Jsonb({"intended_notional": float(Decimal(notional)), "quantity": float(Decimal(quantity)), "orderbook_best_ask": float(Decimal(price))}),
            ),
        )
    return intent_id


def _seed_position(*, entry: str, quantity: str) -> str:
    position_id = uuid4()
    paper_run_id = uuid4()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count, signals_emitted_count,
                metadata_json
            )
            VALUES (%s, 'PAPER_SIM', now(), now(), 'COMPLETED', 1, 1, 1, 1, '{}'::jsonb)
            """,
            (paper_run_id,),
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
                %s, %s, 'payout-position-market', 'YES', %s,
                %s, %s, 0, 0, 'OPEN',
                'ACTIVE', 'NONE', now(), now(),
                NULL, '{}'::jsonb
            )
            """,
            (position_id, paper_run_id, Decimal(quantity), Decimal(entry), Decimal(entry)),
        )
    return str(position_id)


def _safety_counts(conn) -> dict[str, object]:
    counts = {}
    for table in (
        "paper_intents",
        "paper_orders",
        "paper_fills",
        "paper_positions",
        "paper_position_closes",
        "paper_capital_ledger",
        "live_orders",
        "orders_v2",
        "fills_v2",
        "positions",
    ):
        counts[table] = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
    account = conn.execute("SELECT current_balance, available_balance, locked_balance, open_exposure, realized_pnl, unrealized_pnl FROM paper_accounts WHERE account_id='paper_default'").fetchone()
    counts["capital_balances"] = tuple(account.values()) if account else None
    return counts


def _table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])
