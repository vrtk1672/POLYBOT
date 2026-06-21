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
from app.services.capital_efficiency import CapitalEfficiencyService
from app.services.paper_trade_forensics import PaperTradeForensicsService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "brain_dialogue_events",
            "capital_efficiency_sources",
            "capital_efficiency_evaluations",
            "exit_hold_sources",
            "exit_hold_evaluations",
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
        conn.execute(
            """
            INSERT INTO paper_accounts (
                account_id, name, status, initial_balance, current_balance, available_balance, locked_balance, open_exposure,
                realized_pnl, unrealized_pnl, daily_pnl, risk_per_trade_pct, max_position_size,
                max_daily_loss_pct, max_open_positions, max_total_open_exposure_pct, metadata_json,
                created_at, updated_at
            )
            VALUES (
                'paper_default', 'Test Paper', 'ACTIVE', 1000, 1000, 900, 100, 100,
                0, 0, 0, 1, 500,
                5, 10, 25, '{}'::jsonb,
                now(), now()
            )
            ON CONFLICT (account_id) DO UPDATE SET
                current_balance=EXCLUDED.current_balance,
                available_balance=EXCLUDED.available_balance,
                locked_balance=EXCLUDED.locked_balance,
                open_exposure=EXCLUDED.open_exposure,
                realized_pnl=EXCLUDED.realized_pnl,
                unrealized_pnl=EXCLUDED.unrealized_pnl,
                updated_at=now()
            """
        )


def test_open_position_with_lock_and_payout_computes_reward_per_locked_dollar(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_capital_lock(position_id, amount="2")
    _seed_payout("PAPER_POSITION", position_id, stake="2", quantity="10", profit="8")
    _seed_exit_hold("PAPER_POSITION", position_id, exit_pnl="-0.50", potential_reward="8", time_seconds=36000)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        CapitalEfficiencyService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    row = _latest_eval(position_id)
    assert row["capital_locked"] == Decimal("2.00000000")
    assert row["reward_per_locked_dollar"] == Decimal("4.000000000000")


def test_time_to_resolution_computes_reward_per_hour_and_dollar_hour(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_capital_lock(position_id, amount="2")
    _seed_payout("PAPER_POSITION", position_id, stake="2", quantity="10", profit="8")
    _seed_exit_hold("PAPER_POSITION", position_id, exit_pnl="-0.50", potential_reward="8", time_seconds=7200)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        CapitalEfficiencyService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    row = _latest_eval(position_id)
    assert row["reward_per_hour"] == Decimal("4.000000000000")
    assert row["reward_per_dollar_hour"] == Decimal("2.000000000000")


def test_missing_time_records_missing_and_partial_score(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_capital_lock(position_id, amount="2")
    _seed_payout("PAPER_POSITION", position_id, stake="2", quantity="10", profit="8")
    _seed_exit_hold("PAPER_POSITION", position_id, exit_pnl="-0.50", potential_reward="8", time_seconds=None)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        CapitalEfficiencyService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    row = _latest_eval(position_id)
    assert "TIME_TO_RESOLUTION_MISSING" in row["missing_inputs_json"]
    assert row["reward_per_dollar_hour"] is None
    assert row["capital_efficiency_score"] is not None


def test_positive_exit_pnl_weak_hold_upside_creates_release_review(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="1", quantity="100")
    _seed_capital_lock(position_id, amount="100")
    _seed_payout("PAPER_POSITION", position_id, stake="100", quantity="120", profit="20")
    _seed_exit_hold("PAPER_POSITION", position_id, exit_pnl="10", potential_reward="20", time_seconds=20 * 24 * 3600, rules_risk="HIGH", risk_of_reversal="HIGH")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = CapitalEfficiencyService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    assert result["recommendation"] == "CAPITAL_RELEASE_REVIEW"


def test_strong_reward_time_liquidity_creates_support(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.10", quantity="100")
    _seed_capital_lock(position_id, amount="10")
    _seed_payout("PAPER_POSITION", position_id, stake="10", quantity="100", profit="90")
    _seed_exit_hold("PAPER_POSITION", position_id, exit_pnl="-1", potential_reward="90", time_seconds=10 * 3600)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = CapitalEfficiencyService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    assert result["recommendation"] == "CAPITAL_SUPPORT"


def test_poor_liquidity_blocks_or_watches(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_capital_lock(position_id, amount="2")
    _seed_payout("PAPER_POSITION", position_id, stake="2", quantity="10", profit="8")
    _seed_exit_hold("PAPER_POSITION", position_id, exit_pnl="-0.50", potential_reward="8", time_seconds=7200, liquidity="POOR")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = CapitalEfficiencyService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    assert result["recommendation"] in {"CAPITAL_WATCH", "CAPITAL_BLOCK"}


def test_missing_payout_or_exit_data_creates_insufficient_data(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_capital_lock(position_id, amount="2")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = CapitalEfficiencyService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    assert result["recommendation"] == "CAPITAL_INSUFFICIENT_DATA"
    assert "PAYOUT_ODDS_MISSING" in _latest_eval(position_id)["missing_inputs_json"]


def test_source_refs_preserved(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_capital_lock(position_id, amount="2")
    payout_id = _seed_payout("PAPER_POSITION", position_id, stake="2", quantity="10", profit="8")
    exit_id = _seed_exit_hold("PAPER_POSITION", position_id, exit_pnl="-0.50", potential_reward="8", time_seconds=7200)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        CapitalEfficiencyService().evaluate_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    row = _latest_eval(position_id)
    assert row["source_refs_json"]["payout_odds_evaluation_id"] == payout_id
    assert row["source_refs_json"]["exit_hold_evaluation_id"] == exit_id


def test_dashboard_returns_mock_data_false(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_capital_lock(position_id, amount="2")
    _seed_payout("PAPER_POSITION", position_id, stake="2", quantity="10", profit="8")
    _seed_exit_hold("PAPER_POSITION", position_id, exit_pnl="-0.50", potential_reward="8", time_seconds=7200)
    CapitalEfficiencyService().evaluate_recent(subject_type="PAPER_POSITION", limit=10)

    response = TestClient(app).get("/dashboard/api/v2/capital-efficiency")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["total_evaluations"] >= 1


def test_paper_forensics_includes_capital_efficiency_fields(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_capital_lock(position_id, amount="2")
    _seed_payout("PAPER_POSITION", position_id, stake="2", quantity="10", profit="8")
    _seed_exit_hold("PAPER_POSITION", position_id, exit_pnl="-0.50", potential_reward="8", time_seconds=7200)
    CapitalEfficiencyService().evaluate_recent(subject_type="PAPER_POSITION", limit=10)

    trace = PaperTradeForensicsService().get_trade(position_id)

    assert trace["capital_locked"] == 2.0
    assert trace["reward_per_dollar_hour"] == 2.0
    assert trace["capital_allocation_recommendation"] is not None


def test_capital_brain_and_coordinator_visibility_observational(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_capital_lock(position_id, amount="2")
    _seed_payout("PAPER_POSITION", position_id, stake="2", quantity="10", profit="8")
    _seed_exit_hold("PAPER_POSITION", position_id, exit_pnl="-0.50", potential_reward="8", time_seconds=7200)
    CapitalEfficiencyService().evaluate_recent(subject_type="PAPER_POSITION", limit=10)

    capital = CapitalBrainService().dashboard_summary(limit=5)
    coordinator = MeshCoordinatorDecisionService().dashboard_summary(limit=5)

    assert capital["capital_efficiency_observational_only"] is True
    assert coordinator["capital_efficiency_observational_only"] is True


def test_evaluator_does_not_mutate_trading_or_balances(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(entry="0.20", quantity="10")
    _seed_capital_lock(position_id, amount="2")
    _seed_payout("PAPER_POSITION", position_id, stake="2", quantity="10", profit="8")
    _seed_exit_hold("PAPER_POSITION", position_id, exit_pnl="-0.50", potential_reward="8", time_seconds=7200)
    with DatabaseConnectionFactory().connect() as conn:
        before = _safety_counts(conn)

    result = CapitalEfficiencyService().evaluate_recent(subject_type="PAPER_POSITION", limit=10)

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
                %s, %s, 'capital-eff-market', 'YES', %s,
                %s, %s, 0, 0, 'OPEN',
                'ACTIVE', 'NONE', now() - interval '1 hour', now(),
                NULL, '{}'::jsonb
            )
            """,
            (position_id, paper_run_id, Decimal(quantity), Decimal(entry), Decimal(entry)),
        )
    return str(position_id)


def _seed_capital_lock(position_id: str, *, amount: str) -> None:
    amount_d = Decimal(amount)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_capital_ledger (
                ledger_id, account_id, event_type, source_type, source_id,
                paper_position_id, amount, balance_before, balance_after,
                available_before, available_after, locked_before, locked_after,
                reason, metadata_json, created_at
            )
            VALUES (
                %s, 'paper_default', 'CAPITAL_LOCKED_ON_FILL', 'TEST', %s,
                %s, %s, 1000, 1000,
                1000, 1000 - %s, 0, %s,
                'test capital lock', '{}'::jsonb, now() - interval '1 hour'
            )
            """,
            (f"lock-{uuid4().hex}", position_id, position_id, amount_d, amount_d, amount_d),
        )


def _seed_payout(subject_type: str, subject_id: str, *, stake: str, quantity: str, profit: str) -> str:
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
                %s, %s, %s, 'capital-eff-market', 'condition-capital-eff', 'YES', 'token-yes',
                0.20, 'test', %s, %s, %s, %s, %s,
                %s, 1, 0.20, 0.20, 'OK',
                '{}'::jsonb, '{}'::jsonb
            )
            """,
            (evaluation_id, subject_type, subject_id, Decimal(stake), qty, qty, qty, Decimal(profit), Decimal(stake)),
        )
    return evaluation_id


def _seed_exit_hold(
    subject_type: str,
    subject_id: str,
    *,
    exit_pnl: str,
    potential_reward: str,
    time_seconds: int | None,
    liquidity: str = "GOOD",
    rules_risk: str = "LOW",
    risk_of_reversal: str = "UNKNOWN",
) -> str:
    evaluation_id = f"exit-hold-{uuid4().hex}"
    missing = [] if time_seconds is not None else ["TIME_TO_RESOLUTION_MISSING"]
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO exit_hold_evaluations (
                evaluation_id, subject_type, subject_id, paper_position_id, market_id, condition_id, side, token_id,
                cost_basis, quantity, entry_price, current_exit_price, exit_now_value, exit_now_pnl,
                hold_to_resolution_value, hold_to_resolution_profit_if_win, hold_to_resolution_max_loss,
                time_to_resolution_seconds, liquidity_exit_quality, spread_risk, rules_risk, risk_of_reversal,
                decision, confidence, reason, missing_inputs_json, source_refs_json, metadata_json
            )
            VALUES (
                %s, %s, %s, %s, 'capital-eff-market', 'condition-capital-eff', 'YES', 'token-yes',
                2, 10, 0.20, 0.15, 1.5, %s,
                10, %s, 2,
                %s, %s, 'LOW', %s, %s,
                'HOLD_REVIEW', NULL, 'test exit hold', %s, '{}'::jsonb, '{}'::jsonb
            )
            """,
            (
                evaluation_id,
                subject_type,
                subject_id,
                subject_id if subject_type == "PAPER_POSITION" else None,
                Decimal(exit_pnl),
                Decimal(potential_reward),
                time_seconds,
                liquidity,
                rules_risk,
                risk_of_reversal,
                Jsonb(missing),
            ),
        )
    return evaluation_id


def _latest_eval(subject_id: str) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        return conn.execute(
            "SELECT * FROM capital_efficiency_evaluations WHERE subject_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
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
