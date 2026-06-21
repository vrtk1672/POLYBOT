from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.capital_brain.service import CapitalBrainService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import app
from app.mesh_coordinator.service import MeshCoordinatorDecisionService
from app.services.exit_foundation import ExitFoundationService
from app.services.exit_hold_reasoning import ExitHoldReasoningService
from app.services.paper_trade_forensics import PaperTradeForensicsService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "brain_dialogue_events",
            "exit_hold_sources",
            "exit_hold_evaluations",
            "payout_odds_sources",
            "payout_odds_evaluations",
            "position_reactions",
            "paper_position_closes",
            "paper_capital_ledger",
            "paper_trade_ledger",
            "paper_fills",
            "paper_positions",
            "paper_orders",
            "paper_runs",
            "paper_intents",
            "paper_eligibility_candidates",
            "orderbook_snapshots",
            "rules_analysis",
            "market_rules",
            "markets_v2",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def test_open_position_with_best_bid_computes_exit_now_value(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_payout("PAPER_POSITION", position_id, price="0.20", stake="2", quantity="10", profit="8")
    _seed_book(best_bid="0.30")
    _seed_market(close_in_days=10)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        ExitHoldReasoningService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    row = _latest_eval(position_id)
    assert row["exit_now_value"] == Decimal("3.000000")
    assert row["exit_now_pnl"] == Decimal("1.000000")


def test_payout_odds_consumed_for_hold_to_resolution_value(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    payout_id = _seed_payout("PAPER_POSITION", position_id, price="0.20", stake="2", quantity="10", profit="8")
    _seed_book(best_bid="0.21")
    _seed_market(close_in_days=10)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        ExitHoldReasoningService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    row = _latest_eval(position_id)
    assert row["hold_to_resolution_value"] == Decimal("10.000000")
    assert row["hold_to_resolution_profit_if_win"] == Decimal("8.000000")
    assert row["source_refs_json"]["payout_odds_evaluation_id"] == payout_id


def test_positive_exit_pnl_with_small_hold_upside_creates_exit_now(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.80", quantity="10")
    _seed_payout("PAPER_POSITION", position_id, price="0.80", stake="8", quantity="10", profit="2")
    _seed_book(best_bid="0.99")
    _seed_market(close_in_days=10)
    _seed_rules(recommendation="TRADE_ALLOWED", wording="0", dispute="0")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = ExitHoldReasoningService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    assert result["decision"] == "EXIT_NOW"
    assert _latest_eval(position_id)["confidence"] is None


def test_short_time_to_resolution_with_stable_risk_creates_hold_to_resolution(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_payout("PAPER_POSITION", position_id, price="0.20", stake="2", quantity="10", profit="8")
    _seed_book(best_bid="0.30")
    _seed_market(close_in_days=1)
    _seed_rules(recommendation="TRADE_ALLOWED", wording="0", dispute="0")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = ExitHoldReasoningService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    assert result["decision"] == "HOLD_TO_RESOLUTION"


def test_profit_plus_rising_risk_creates_partial_exit_review(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_payout("PAPER_POSITION", position_id, price="0.20", stake="2", quantity="10", profit="8")
    _seed_book(best_bid="0.30")
    _seed_market(close_in_days=10)
    _seed_rules(recommendation="PENALIZE_HEAVILY", wording="0.5", dispute="0.6")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = ExitHoldReasoningService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    assert result["decision"] == "PARTIAL_EXIT_REVIEW"


def test_missing_book_creates_emergency_review_and_missing_reason(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_payout("PAPER_POSITION", position_id, price="0.20", stake="2", quantity="10", profit="8")
    _seed_market(close_in_days=10)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = ExitHoldReasoningService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    row = _latest_eval(position_id)
    assert result["decision"] == "EMERGENCY_EXIT_REVIEW"
    assert "EXIT_NOW_UNAVAILABLE" in row["missing_inputs_json"]


def test_missing_payout_odds_creates_insufficient_data(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_book(best_bid="0.25")
    _seed_market(close_in_days=10)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = ExitHoldReasoningService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    assert result["decision"] == "INSUFFICIENT_DATA"
    assert "PAYOUT_ODDS_MISSING" in _latest_eval(position_id)["missing_inputs_json"]


def test_missing_time_and_rules_are_not_faked(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_payout("PAPER_POSITION", position_id, price="0.20", stake="2", quantity="10", profit="8")
    _seed_book(best_bid="0.25")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        ExitHoldReasoningService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    row = _latest_eval(position_id)
    assert row["time_to_resolution_seconds"] is None
    assert "TIME_TO_RESOLUTION_MISSING" in row["missing_inputs_json"]
    assert row["rules_risk"] == "RULES_RISK_UNKNOWN"


def test_source_refs_preserved(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    payout_id = _seed_payout("PAPER_POSITION", position_id, price="0.20", stake="2", quantity="10", profit="8")
    _seed_book(best_bid="0.25")
    _seed_market(close_in_days=10)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        ExitHoldReasoningService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    with DatabaseConnectionFactory().connect() as conn:
        row = _latest_eval(position_id)
        sources = conn.execute("SELECT source_table FROM exit_hold_sources WHERE evaluation_id=%s ORDER BY source_table", (row["evaluation_id"],)).fetchall()
    assert row["source_refs_json"]["payout_odds_evaluation_id"] == payout_id
    assert {"paper_positions", "payout_odds_evaluations", "orderbook_snapshots", "markets_v2"} <= {item["source_table"] for item in sources}


def test_paper_forensics_includes_exit_hold_fields(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_payout("PAPER_POSITION", position_id, price="0.20", stake="2", quantity="10", profit="8")
    _seed_book(best_bid="0.25")
    _seed_market(close_in_days=10)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        ExitHoldReasoningService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    trace = PaperTradeForensicsService().get_trade(position_id)

    assert trace["exit_hold_decision"] is not None
    assert trace["exit_now_value"] == 2.5
    assert trace["hold_to_resolution_profit_if_win"] == 8.0


def test_dashboard_returns_mock_data_false(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_payout("PAPER_POSITION", position_id, price="0.20", stake="2", quantity="10", profit="8")
    _seed_book(best_bid="0.25")
    _seed_market(close_in_days=10)
    ExitHoldReasoningService().evaluate_recent(subject_type="PAPER_POSITION", limit=10)

    response = TestClient(app).get("/dashboard/api/v2/exit-hold")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["total_evaluations"] >= 1


def test_capital_exit_coordinator_visibility_observational_only(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_payout("PAPER_POSITION", position_id, price="0.20", stake="2", quantity="10", profit="8")
    _seed_book(best_bid="0.25")
    _seed_market(close_in_days=10)
    ExitHoldReasoningService().evaluate_recent(subject_type="PAPER_POSITION", limit=10)

    capital = CapitalBrainService().dashboard_summary(limit=5)
    exit_payload = ExitFoundationService().get_dashboard_summary(limit=5)
    coordinator = MeshCoordinatorDecisionService().dashboard_summary(limit=5)

    assert capital["exit_hold_observational_only"] is True
    assert exit_payload["exit_hold_observational_only"] is True
    assert coordinator["exit_hold_observational_only"] is True


def test_evaluator_does_not_auto_close_or_mutate_trading_tables(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_payout("PAPER_POSITION", position_id, price="0.20", stake="2", quantity="10", profit="8")
    _seed_book(best_bid="0.25")
    _seed_market(close_in_days=10)
    with DatabaseConnectionFactory().connect() as conn:
        before = _safety_counts(conn)

    result = ExitHoldReasoningService().evaluate_recent(subject_type="PAPER_POSITION", limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        after = _safety_counts(conn)
    assert result["trading_mutation"] is False
    assert before == after


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
                %s, %s, 'exit-hold-market', 'YES', %s,
                %s, %s, 0, 0, 'OPEN',
                'ACTIVE', 'NONE', now(), now(),
                NULL, '{}'::jsonb
            )
            """,
            (position_id, paper_run_id, Decimal(quantity), Decimal(entry), Decimal(entry)),
        )
    return str(position_id)


def _seed_payout(subject_type: str, subject_id: str, *, price: str, stake: str, quantity: str, profit: str) -> str:
    evaluation_id = f"payout-{uuid4().hex}"
    qty = Decimal(quantity)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO payout_odds_evaluations (
                evaluation_id, subject_type, subject_id, market_id, condition_id, side, token_id,
                price, price_source, stake_usd, quantity, shares_if_buy, payout_if_win, profit_if_win,
                max_loss, risk_reward, implied_probability, break_even_probability, settlement_value_status,
                source_refs_json, metadata_json
            )
            VALUES (
                %s, %s, %s, 'exit-hold-market', 'condition-exit-hold', 'YES', 'token-yes',
                %s, 'test', %s, %s, %s, %s, %s,
                %s, 1, %s, %s, 'OK',
                '{}'::jsonb, '{}'::jsonb
            )
            """,
            (
                evaluation_id,
                subject_type,
                subject_id,
                Decimal(price),
                Decimal(stake),
                qty,
                qty,
                qty,
                Decimal(profit),
                Decimal(stake),
                Decimal(price),
                Decimal(price),
            ),
        )
    return evaluation_id


def _seed_book(*, best_bid: str) -> None:
    bid = Decimal(best_bid)
    ask = bid + Decimal("0.01")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask, spread, mid_price,
                depth_1c, depth_2c, depth_5c, bid_depth_json, ask_depth_json, imbalance,
                snapshot_at, raw_orderbook_json, metadata_json, liquidity_score, source, snapshot_status,
                is_stale, collected_at
            )
            VALUES (
                %s, 'exit-hold-market', 'token-yes', 'YES', %s, %s, 0.01, %s,
                100, 100, 100, '[]'::jsonb, '[]'::jsonb, 0,
                now(), '{}'::jsonb, '{}'::jsonb, 0.90, 'test', 'OK',
                false, now()
            )
            """,
            (f"book-{uuid4().hex}", bid, ask, (bid + ask) / 2),
        )


def _seed_market(*, close_in_days: int) -> None:
    deadline = datetime.now(UTC) + timedelta(days=close_in_days)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, condition_id, question, yes_token_id, no_token_id, close_time, created_at, updated_at
            )
            VALUES ('exit-hold-market', 'condition-exit-hold', 'test market', 'token-yes', 'token-no', %s, now(), now())
            ON CONFLICT (market_id) DO UPDATE SET close_time=EXCLUDED.close_time, updated_at=now()
            """,
            (deadline,),
        )


def _seed_rules(*, recommendation: str, wording: str, dispute: str) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO rules_analysis (
                rules_analysis_id, market_id, rules_hash, rules_text_present, resolution_source_present,
                deadline_present, wording_risk, dispute_risk, resolution_clarity, source_verification_status,
                jurisdiction_status, compliance_status, recommendation, created_at, metadata_json
            )
            VALUES (
                %s, 'exit-hold-market', 'rules-hash', true, true,
                true, %s, %s, 1, 'VERIFIED',
                'VERIFIED', 'CLEAR', %s, now(), '{}'::jsonb
            )
            """,
            (f"rules-{uuid4().hex}", Decimal(wording), Decimal(dispute), recommendation),
        )


def _latest_eval(subject_id: str) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        return conn.execute(
            "SELECT * FROM exit_hold_evaluations WHERE subject_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
            (subject_id,),
        ).fetchone()


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
