from __future__ import annotations

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
from app.services.paper_trade_forensics import PaperTradeForensicsService
from app.services.trade_lifecycle import TradeLifecycleService


MARKET_ID = "lifecycle-market"
SIDE = "YES"


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "brain_dialogue_events",
            "trade_lifecycle_brain_contributions",
            "trade_lifecycle_plan_sources",
            "trade_lifecycle_plans",
            "capital_efficiency_sources",
            "capital_efficiency_evaluations",
            "exit_hold_sources",
            "exit_hold_evaluations",
            "payout_odds_sources",
            "payout_odds_evaluations",
            "same_market_side_guard_decisions",
            "mesh_conflict_records",
            "mesh_coordinator_decision_sources",
            "mesh_coordinator_decisions",
            "mesh_coordinator_input_bundles",
            "mesh_brain_consumption_sources",
            "mesh_brain_opinions",
            "mesh_awareness_sources",
            "mesh_shared_awareness",
            "mesh_session_events",
            "mesh_session_participants",
            "mesh_session_state",
            "mesh_sessions",
            "position_reactions",
            "position_awareness",
            "open_position_watchdog_traces",
            "same_market_side_guard_decisions",
            "news_impact_scores",
            "whale_events",
            "whale_scan_runs",
            "market_memory_v2",
            "rules_analysis",
            "orderbook_snapshots",
            "risk_decisions",
            "exit_plan_rules",
            "exit_plans",
            "capital_brain_evaluations",
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
                'paper_default', 'Test Paper', 'ACTIVE', 1000, 1000, 990, 10, 10,
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


def test_plan_aggregates_all_brain_sources_and_can_be_complete(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position()
    _seed_full_context("PAPER_POSITION", position_id, position_id=position_id, include_optional=True)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = TradeLifecycleService().build_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    row = _latest_plan(position_id)
    assert result["plan_status"] == "COMPLETE"
    assert row["payout_summary_json"]["evaluation_id"].startswith("payout-")
    assert row["exit_hold_summary_json"]["decision"] == "HOLD_REVIEW"
    assert row["capital_efficiency_summary_json"]["recommendation"] == "CAPITAL_SUPPORT"
    assert row["same_market_summary_json"]["decision"] == "ALLOW"
    assert row["risk_summary_json"]["decision"] == "APPROVE"
    assert row["coordinator_judgment_json"]["final_action"] == "HOLD_REVIEW"
    assert _source_count(row["plan_id"]) >= 12
    assert _contribution_names(row["plan_id"]) >= {
        "Payout/Odds",
        "Exit/Hold",
        "Capital Efficiency",
        "Same-Market Guard",
        "Risk",
        "Exit Foundation",
        "Capital Brain",
        "Orderbook/Liquidity",
        "Position Watchdog",
        "Rules/Wording",
        "News/AI Context",
        "Whale",
        "Memory",
        "Coordinator",
    }


def test_missing_sources_are_recorded_not_faked(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position()
    _seed_payout("PAPER_POSITION", position_id)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        TradeLifecycleService().build_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    row = _latest_plan(position_id)
    missing = set(row["missing_inputs_json"])
    assert "EXIT_HOLD_MISSING" in missing
    assert "CAPITAL_EFFICIENCY_MISSING" in missing
    assert "NEWS_CONTEXT_MISSING" in missing
    assert "WHALE_CONTEXT_MISSING" in missing
    assert "fair probability is not source-backed" in row["economic_thesis"]
    assert row["payout_summary_json"]["fair_probability"] is None
    assert row["payout_summary_json"]["expected_value"] is None


def test_partial_plan_when_time_news_whale_memory_missing(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position()
    _seed_full_context("PAPER_POSITION", position_id, position_id=position_id, include_optional=False, time_seconds=None)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = TradeLifecycleService().build_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    row = _latest_plan(position_id)
    assert result["plan_status"] == "WATCH"
    assert "TIME_TO_RESOLUTION_MISSING" in row["missing_inputs_json"]
    assert "NEWS_CONTEXT_MISSING" in row["missing_inputs_json"]
    assert "WHALE_CONTEXT_MISSING" in row["missing_inputs_json"]
    assert "MEMORY_CONTEXT_MISSING" in row["missing_inputs_json"]


def test_open_position_plan_includes_monitoring_plan(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position()
    _seed_full_context("PAPER_POSITION", position_id, position_id=position_id, include_optional=True)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        TradeLifecycleService().build_subject_with_conn(conn, subject_type="PAPER_POSITION", subject_id=position_id)

    monitoring = _latest_plan(position_id)["monitoring_plan_json"]
    domains = {item["domain"]: item for item in monitoring}
    assert domains["orderbook_watcher"]["source_backed_now"] is True
    assert domains["position_watchdog"]["source_backed_now"] is True
    assert domains["capital_reconciliation"]["source_backed_now"] is True


def test_blocked_same_market_plan_becomes_blocked_no_trade(postgres_test_schema) -> None:
    _prepare()
    candidate_id = _seed_candidate()
    _seed_full_context("PAPER_CANDIDATE", candidate_id, include_optional=True, guard_decision="BLOCK")

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = TradeLifecycleService().build_subject_with_conn(conn, subject_type="PAPER_CANDIDATE", subject_id=candidate_id)

    row = _latest_plan(candidate_id)
    assert result["strategy_type"] == "SAME_MARKET_BLOCKED"
    assert row["plan_status"] == "BLOCKED"
    assert row["decision_class"] == "BLOCKED"
    assert row["same_market_summary_json"]["blocker_reason"] == "SAME_MARKET_OPPOSING_SIDE_BLOCK"


def test_paper_intent_plan_is_context_only(postgres_test_schema) -> None:
    _prepare()
    intent_id = _seed_intent()
    _seed_full_context("PAPER_INTENT", intent_id, include_optional=True)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = TradeLifecycleService().build_subject_with_conn(conn, subject_type="PAPER_INTENT", subject_id=intent_id)

    row = _latest_plan(intent_id)
    assert result["subject_type"] == "PAPER_INTENT"
    assert row["metadata_json"]["observational_only"] is True
    assert row["metadata_json"]["no_trading_mutation"] is True
    assert row["decision_class"] in {"PAPER_INTENT_READY_CONTEXT", "WATCH"}


def test_dashboard_returns_mock_data_false(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position()
    _seed_full_context("PAPER_POSITION", position_id, position_id=position_id, include_optional=True)
    TradeLifecycleService().build_recent(subject_type="PAPER_POSITION", limit=10)

    response = TestClient(app).get("/dashboard/api/v2/trade-lifecycle")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["total_plans"] >= 1
    assert payload["plans_by_subject_type"]["PAPER_POSITION"] >= 1


def test_paper_forensics_includes_lifecycle_plan(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position()
    _seed_full_context("PAPER_POSITION", position_id, position_id=position_id, include_optional=True)
    TradeLifecycleService().build_recent(subject_type="PAPER_POSITION", limit=10)

    trace = PaperTradeForensicsService().get_trade(position_id)

    assert trace["lifecycle_plan_status"] == "COMPLETE"
    assert trace["trade_lifecycle_plan"]["strategy_type"] == "HOLD_REVIEW"
    assert trace["lifecycle_brain_contributions"]


def test_capital_exit_coordinator_visibility_is_observational(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position()
    _seed_full_context("PAPER_POSITION", position_id, position_id=position_id, include_optional=True)
    TradeLifecycleService().build_recent(subject_type="PAPER_POSITION", limit=10)

    capital = CapitalBrainService().dashboard_summary(limit=5)
    exit_foundation = ExitFoundationService().get_dashboard_summary(limit=5)
    coordinator = MeshCoordinatorDecisionService().dashboard_summary(limit=5)

    assert capital["trade_lifecycle_observational_only"] is True
    assert exit_foundation["trade_lifecycle_observational_only"] is True
    assert coordinator["trade_lifecycle_observational_only"] is True


def test_builder_does_not_mutate_paper_live_or_capital(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position()
    _seed_full_context("PAPER_POSITION", position_id, position_id=position_id, include_optional=True)
    with DatabaseConnectionFactory().connect() as conn:
        before = _safety_counts(conn)

    result = TradeLifecycleService().build_recent(subject_type="PAPER_POSITION", limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        after = _safety_counts(conn)
    assert result["trading_mutation"] is False
    assert before == after


def _seed_position() -> str:
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
                %s, %s, %s, %s, 10,
                0.20, 0.20, 0, 0, 'OPEN',
                'ACTIVE', 'NONE', now() - interval '1 hour', now(),
                NULL, %s
            )
            """,
            (
                position_id,
                paper_run_id,
                MARKET_ID,
                SIDE,
                Jsonb({"risk_decision_id": f"risk-{position_id}", "exit_plan_id": f"exit-{position_id}", "orderbook_snapshot_id": "1"}),
            ),
        )
    return str(position_id)


def _seed_candidate() -> str:
    candidate_id = f"candidate-{uuid4().hex}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, thesis_id, risk_decision_id, exit_plan_id, coordinator_decision_id,
                brain_output_ids, signal_ids, market_id, side, status, eligibility_score,
                eligibility_blockers, missing_requirements, evidence, risk_approved, exit_ready,
                not_dry_run, paper_intent_allowed, execution_allowed, generated_by, producer_name,
                is_runtime_generated, is_dry_run_generated
            )
            VALUES (
                %s, %s, %s, %s, %s,
                '[]'::jsonb, '[]'::jsonb, %s, %s, 'ELIGIBLE', 0.8,
                '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, true, true,
                true, false, false, 'test', 'test',
                true, false
            )
            """,
            (candidate_id, f"thesis-{candidate_id}", f"risk-{candidate_id}", f"exit-{candidate_id}", f"coord-{candidate_id}", MARKET_ID, SIDE),
        )
    return candidate_id


def _seed_intent() -> str:
    intent_id = f"intent-{uuid4().hex}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id, exit_plan_id, coordinator_decision_id,
                market_id, side, price_basis, intended_price, confidence, intent_status, intent_type, intent_reason,
                evidence, blockers, paper_only, live, execution_allowed, order_intent_created, generated_by, producer_name,
                is_runtime_generated, is_dry_run_generated
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, 'ORDERBOOK_BEST_ASK', 0.20, 0.7, 'CREATED', 'PAPER_ENTRY_INTENT', 'test intent',
                '{}'::jsonb, '[]'::jsonb, true, false, false, false, 'test', 'test',
                true, false
            )
            """,
            (intent_id, f"elig-{intent_id}", f"thesis-{intent_id}", f"risk-{intent_id}", f"exit-{intent_id}", f"coord-{intent_id}", MARKET_ID, SIDE),
        )
    return intent_id


def _seed_full_context(
    subject_type: str,
    subject_id: str,
    *,
    position_id: str | None = None,
    include_optional: bool,
    time_seconds: int | None = 3600,
    guard_decision: str = "ALLOW",
) -> None:
    orderbook_id = _seed_orderbook()
    _seed_payout(subject_type, subject_id)
    if subject_type != "FRESH_SEED":
        _seed_exit_hold(subject_type, subject_id, position_id=position_id, time_seconds=time_seconds)
    _seed_capital_efficiency(subject_type, subject_id, position_id=position_id, time_seconds=time_seconds)
    _seed_guard(subject_type, subject_id, guard_decision=guard_decision)
    _seed_risk(subject_id, orderbook_id=orderbook_id)
    _seed_exit_plan(subject_id, orderbook_id=orderbook_id)
    session_id = _seed_mesh(subject_id, subject_type=subject_type, position_id=position_id)
    _seed_capital_brain(session_id, subject_id, position_id=position_id)
    _seed_rules()
    if position_id:
        _seed_position_awareness(position_id, session_id)
    if include_optional:
        _seed_news()
        _seed_whale()
        _seed_memory()


def _seed_payout(subject_type: str, subject_id: str) -> str:
    evaluation_id = f"payout-{uuid4().hex}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO payout_odds_evaluations (
                evaluation_id, subject_type, subject_id, market_id, condition_id, side, token_id,
                price, price_source, stake_usd, quantity, shares_if_buy, payout_if_win, profit_if_win,
                max_loss, risk_reward, implied_probability, break_even_probability, fair_probability, expected_value,
                settlement_value_status, source_refs_json, metadata_json
            )
            VALUES (
                %s, %s, %s, %s, 'condition-life', %s, 'token-yes',
                0.20, 'test', 2, 10, 10, 10, 8,
                2, 4, 0.20, 0.20, NULL, NULL,
                'OK', '{}'::jsonb, '{}'::jsonb
            )
            """,
            (evaluation_id, subject_type, subject_id, MARKET_ID, SIDE),
        )
    return evaluation_id


def _seed_exit_hold(subject_type: str, subject_id: str, *, position_id: str | None, time_seconds: int | None) -> str:
    evaluation_id = f"exit-hold-{uuid4().hex}"
    missing = [] if time_seconds is not None else ["TIME_TO_RESOLUTION_MISSING"]
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO exit_hold_evaluations (
                evaluation_id, subject_type, subject_id, paper_position_id, market_id, condition_id, side, token_id,
                cost_basis, quantity, entry_price, current_exit_price, exit_now_value, exit_now_pnl,
                hold_to_resolution_value, hold_to_resolution_profit_if_win, hold_to_resolution_max_loss,
                time_to_resolution_seconds, liquidity_exit_quality, spread, spread_risk, rules_risk, risk_of_reversal,
                decision, confidence, reason, missing_inputs_json, source_refs_json, metadata_json
            )
            VALUES (
                %s, %s, %s, %s, %s, 'condition-life', %s, 'token-yes',
                2, 10, 0.20, 0.15, 1.5, -0.5,
                10, 8, 2,
                %s, 'GOOD', 0.01, 'LOW', 'LOW', 'UNKNOWN',
                'HOLD_REVIEW', NULL, 'source-backed hold review', %s, '{}'::jsonb, '{}'::jsonb
            )
            """,
            (evaluation_id, subject_type, subject_id, position_id, MARKET_ID, SIDE, time_seconds, Jsonb(missing)),
        )
    return evaluation_id


def _seed_capital_efficiency(subject_type: str, subject_id: str, *, position_id: str | None, time_seconds: int | None) -> str:
    evaluation_id = f"cap-eff-{uuid4().hex}"
    missing = [] if time_seconds is not None else ["TIME_TO_RESOLUTION_MISSING"]
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO capital_efficiency_evaluations (
                evaluation_id, subject_type, subject_id, paper_position_id, market_id, condition_id, side, token_id,
                capital_locked, time_locked_seconds, time_to_resolution_seconds, current_exit_pnl, potential_reward, risk_amount,
                reward_per_locked_dollar, reward_per_hour, reward_per_dollar_hour, current_return_pct, hold_return_pct,
                open_exposure, available_balance, liquidity_exit_quality, rules_risk, risk_of_reversal, capital_efficiency_score,
                recommendation, confidence, reason, missing_inputs_json, source_refs_json, metadata_json
            )
            VALUES (
                %s, %s, %s, %s, %s, 'condition-life', %s, 'token-yes',
                2, 3600, %s, -0.5, 8, 2,
                4, 8, 4, -0.25, 4,
                10, 990, 'GOOD', 'LOW', 'UNKNOWN', 0.82,
                'CAPITAL_SUPPORT', NULL, 'source-backed capital support', %s, '{}'::jsonb, '{}'::jsonb
            )
            """,
            (evaluation_id, subject_type, subject_id, position_id, MARKET_ID, SIDE, time_seconds, Jsonb(missing)),
        )
    return evaluation_id


def _seed_guard(subject_type: str, subject_id: str, *, guard_decision: str) -> str:
    decision_id = f"guard-{uuid4().hex}"
    blocker = "SAME_MARKET_OPPOSING_SIDE_BLOCK" if guard_decision == "BLOCK" else None
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO same_market_side_guard_decisions (
                decision_id, market_id, proposed_side, proposed_candidate_id, proposed_intent_id,
                existing_exposure_json, existing_open_positions_count, existing_opposite_positions_count,
                existing_same_side_positions_count, existing_opposite_intents_count, existing_same_side_intents_count,
                recent_opposite_closes_count, batch_opposite_candidates_count, rationale_type, rationale_source,
                source_backed, decision, blocker_reason, dry_run, metadata_json
            )
            VALUES (
                %s, %s, %s, %s, %s,
                '{}'::jsonb, 0, 0,
                0, 0, 0,
                0, 0, NULL, NULL,
                false, %s, %s, false, '{}'::jsonb
            )
            """,
            (
                decision_id,
                MARKET_ID,
                SIDE,
                subject_id if subject_type in {"FRESH_SEED", "PAPER_CANDIDATE"} else None,
                subject_id if subject_type == "PAPER_INTENT" else None,
                guard_decision,
                blocker,
            ),
        )
    return decision_id


def _seed_risk(subject_id: str, *, orderbook_id: int) -> str:
    risk_id = f"risk-{subject_id}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO risk_decisions (
                risk_decision_id, thesis_id, market_id, decision, risk_status, risk_score, confidence,
                max_position_size, max_loss, market_risk_score, liquidity_risk_score, spread_risk_score,
                missing_data_risk_score, confidence_risk_score, daily_exposure_risk_score,
                risk_reasons, blockers, warnings, required_missing_evidence, source_thesis_status,
                orderbook_snapshot_id, paper_candidate_allowed, execution_allowed, risk_approved, exit_required,
                generated_by, producer_name, is_runtime_generated, is_dry_run_generated
            )
            VALUES (
                %s, %s, %s, 'APPROVE', 'LOW', 0.2, 0.7,
                10, 5, 0.1, 0.1, 0.1,
                0, 0, 0,
                '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 'COMPLETE',
                %s, false, false, true, true,
                'test', 'risk_core', true, false
            )
            """,
            (risk_id, f"thesis-{subject_id}", MARKET_ID, orderbook_id),
        )
    return risk_id


def _seed_exit_plan(subject_id: str, *, orderbook_id: int) -> str:
    exit_id = f"exit-{subject_id}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO exit_plans (
                exit_plan_id, market_id, side, engine, entry_price, entry_size, target_exit, stop_loss,
                max_hold_seconds, invalidation_rule_json, liquidity_exit_check_json, emergency_exit_json,
                momentum_decay_exit_json, spread_exit_json, news_invalidated_exit_json, exit_mode,
                plan_status, created_from, data_confidence, insufficient_data, insufficient_data_reasons_json,
                thesis_id, risk_decision_ref, status, exit_type, invalidation_rules, emergency_exit_rules,
                liquidity_exit_check, time_exit_check, missing_exit_evidence, blockers, warnings,
                source_risk_status, source_risk_score, orderbook_snapshot_id, paper_intent_allowed, paper_exit_ready,
                execution_allowed, generated_by, producer_name, is_runtime_generated, is_dry_run_generated
            )
            VALUES (
                %s, %s, %s, 'EXIT_FOUNDATION', 0.20, 10, 0.40, 0.10,
                3600, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
                '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, 'PAPER_SIM_EXIT',
                'ACTIVE', 'test', 0.8, false, '[]'::jsonb,
                %s, %s, 'COMPLETE', 'BASIC_PROTECTIVE_EXIT', '[]'::jsonb, '[]'::jsonb,
                '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                'LOW', 0.2, %s, false, true,
                false, 'test', 'exit_foundation', true, false
            )
            """,
            (exit_id, MARKET_ID, SIDE, f"thesis-{subject_id}", f"risk-{subject_id}", orderbook_id),
        )
    return exit_id


def _seed_orderbook() -> int:
    snapshot_id = f"ob-{uuid4().hex}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        row = conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask, spread, mid_price,
                depth_1c, depth_2c, depth_5c, bid_depth_json, ask_depth_json, liquidity_score,
                source, snapshot_status, is_stale
            )
            VALUES (
                %s, %s, 'token-yes', %s, 0.19, 0.20, 0.01, 0.195,
                100, 200, 300, '[]'::jsonb, '[]'::jsonb, 0.8,
                'test', 'OK', false
            )
            RETURNING id
            """,
            (snapshot_id, MARKET_ID, SIDE),
        ).fetchone()
    return int(row["id"])


def _seed_mesh(subject_id: str, *, subject_type: str, position_id: str | None) -> str:
    session_id = f"session-{uuid4().hex}"
    candidate_id = subject_id if subject_type in {"FRESH_SEED", "PAPER_CANDIDATE"} else None
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO mesh_sessions (
                session_id, session_type, market_id, candidate_id, position_id, title, status, priority,
                participant_count, has_decision, opportunity_context, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, 'test lifecycle session', 'ACTIVE', 5, 1, true, true, '{}'::jsonb)
            """,
            (session_id, "POSITION_SESSION" if position_id else "CANDIDATE_SESSION", MARKET_ID, candidate_id, position_id),
        )
        conn.execute(
            """
            INSERT INTO mesh_shared_awareness (
                awareness_id, session_id, session_type, market_id, candidate_id, position_id, status, freshness_status,
                completeness_score, confidence_score, missing_domains_json, stale_domains_json, source_counts_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'ACTIVE', 'FRESH', 1, 0.8, '[]'::jsonb, '[]'::jsonb, '{}'::jsonb)
            """,
            (f"aware-{session_id}", session_id, "POSITION_SESSION" if position_id else "CANDIDATE_SESSION", MARKET_ID, candidate_id, position_id),
        )
        conn.execute(
            """
            INSERT INTO mesh_brain_opinions (
                opinion_id, session_id, brain_name, brain_type, market_id, candidate_id, position_id,
                stance, confidence, decision_bias, reasoning_summary
            )
            VALUES (%s, %s, 'Capital Brain', 'CAPITAL_BRAIN', %s, %s, %s, 'SUPPORT', 0.7, 'OBSERVE', 'source-backed support')
            """,
            (f"opinion-{session_id}", session_id, MARKET_ID, candidate_id, position_id),
        )
        conn.execute(
            """
            INSERT INTO mesh_coordinator_input_bundles (
                bundle_id, session_id, market_id, candidate_id, position_id, source_brain_count,
                opinion_count, stance_summary_json, coordinator_ready
            )
            VALUES (%s, %s, %s, %s, %s, 1, 1, '{}'::jsonb, true)
            """,
            (f"bundle-{session_id}", session_id, MARKET_ID, candidate_id, position_id),
        )
        conn.execute(
            """
            INSERT INTO mesh_coordinator_decisions (
                decision_id, session_id, bundle_id, market_id, candidate_id, position_id,
                final_stance, final_action, confidence, source_brain_count, opinion_count,
                conflicts_detected, conflict_count, decision_reason, safety_status, coordinator_ready
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                'WATCH', %s, 0.7, 1, 1,
                false, 0, 'source-backed lifecycle test coordinator', 'SAFE_NON_EXECUTING', true
            )
            """,
            (f"coord-{subject_id}", session_id, f"bundle-{session_id}", MARKET_ID, candidate_id, position_id, "HOLD_REVIEW" if position_id else "PAPER_CANDIDATE_REVIEW"),
        )
    return session_id


def _seed_capital_brain(session_id: str, subject_id: str, *, position_id: str | None) -> str:
    evaluation_id = f"capital-brain-{uuid4().hex}"
    candidate_id = subject_id if position_id is None else None
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO capital_brain_evaluations (
                evaluation_id, session_id, market_id, candidate_id, position_id, account_id,
                available_balance, locked_balance, current_balance, open_exposure, daily_pnl,
                risk_per_trade_pct, max_position_size, max_daily_loss_pct, max_open_positions,
                max_total_open_exposure_pct, estimated_required_capital, estimated_max_loss,
                estimated_capital_lock_minutes, capital_efficiency_score, exposure_fit_score,
                balance_fit_score, decision, confidence, reason, missing_inputs_json, risk_flags_json
            )
            VALUES (
                %s, %s, %s, %s, %s, 'paper_default',
                990, 10, 1000, 10, 0,
                1, 500, 5, 10,
                25, 2, 2,
                60, 0.8, 0.9,
                0.9, 'CAPITAL_SUPPORT', 0.75, 'source-backed capital brain support', '[]'::jsonb, '[]'::jsonb
            )
            """,
            (evaluation_id, session_id, MARKET_ID, candidate_id, position_id),
        )
    return evaluation_id


def _seed_position_awareness(position_id: str, session_id: str) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO position_awareness (
                awareness_id, position_id, session_id, market_id, side, entry_price, current_price, pnl,
                pnl_pct, exposure, age_minutes, liquidity_status, risk_status, exit_status, capital_status,
                coordinator_status, awareness_score
            )
            VALUES (%s, %s, %s, %s, %s, 0.20, 0.20, 0, 0, 2, 60, 'GOOD', 'LOW', 'HOLD', 'LOCKED', 'WATCH', 0.9)
            """,
            (f"pos-aware-{uuid4().hex}", position_id, session_id, MARKET_ID, SIDE),
        )


def _seed_rules() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO rules_analysis (
                rules_analysis_id, market_id, rules_hash, rules_text_present, resolution_source_present,
                deadline_present, settlement_method, deadline_at, wording_risk, dispute_risk,
                resolution_clarity, source_verification_status, jurisdiction_status, compliance_status,
                recommendation
            )
            VALUES (%s, %s, 'hash', true, true, true, 'binary', now() + interval '1 day', 0.1, 0.1, 0.9, 'VERIFIED', 'CLEAR', 'CLEAR', 'TRADE_ALLOWED')
            """,
            (f"rules-{uuid4().hex}", MARKET_ID),
        )


def _seed_news() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO news_impact_scores (
                impact_id, news_event_id, market_id, direction, strength, confidence, urgency,
                already_priced_in, ttl_seconds, source_reliability, reason
            )
            VALUES (%s, %s, %s, 'UNKNOWN', 0.1, 0.6, 0.1, 0.5, 3600, 0.7, 'test news context')
            """,
            (f"impact-{uuid4().hex}", f"news-{uuid4().hex}", MARKET_ID),
        )


def _seed_whale() -> None:
    run_id = uuid4()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO whale_scan_runs (
                id, source_type, source_ref, status, scanner_version, started_at, ended_at,
                input_count, success_count, failure_count, metadata_json
            )
            VALUES (%s, 'test', 'trade-lifecycle-test', 'COMPLETED', 'test', now(), now(), 1, 1, 0, '{}'::jsonb)
            """,
            (run_id,),
        )
        conn.execute(
            """
            INSERT INTO whale_events (
                id, whale_scan_run_id, wallet_address, market_id, event_timestamp, event_direction_class,
                side_or_outcome, size, notional, price, source_type, detection_reason_code,
                detection_reason_text, whale_event_id, confidence
            )
            VALUES (%s, %s, 'wallet-test', %s, now(), 'UNKNOWN', %s, 1, 1, 0.20, 'test', 'TEST', 'test whale context', %s, 0.6)
            """,
            (uuid4(), run_id, MARKET_ID, SIDE, f"whale-{uuid4().hex}"),
        )


def _seed_memory() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO market_memory_v2 (market_id, market_slug, question, market_family, observations_count, memory_confidence, memory_status)
            VALUES (%s, 'lifecycle', 'Lifecycle test market?', 'test', 1, 0.6, 'active')
            """,
            (MARKET_ID,),
        )


def _latest_plan(subject_id: str) -> dict:
    with DatabaseConnectionFactory().connect() as conn:
        return dict(
            conn.execute(
                "SELECT * FROM trade_lifecycle_plans WHERE subject_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
                (subject_id,),
            ).fetchone()
        )


def _source_count(plan_id: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        return int(conn.execute("SELECT COUNT(*) AS count FROM trade_lifecycle_plan_sources WHERE plan_id=%s", (plan_id,)).fetchone()["count"])


def _contribution_names(plan_id: str) -> set[str]:
    with DatabaseConnectionFactory().connect() as conn:
        return {row["brain_name"] for row in conn.execute("SELECT brain_name FROM trade_lifecycle_brain_contributions WHERE plan_id=%s", (plan_id,)).fetchall()}


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
