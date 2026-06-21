from __future__ import annotations

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations

SESSION_ID = "paper-session-autopsy"


def prepare_autopsy_fixture(*, mode: str = "PAPER") -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "candidate_eligibility_recovery_runs",
            "paper_execution_runs",
            "paper_exit_loop_runs",
            "paper_position_closes",
            "paper_fills",
            "paper_positions",
            "paper_orders",
            "paper_intents",
            "paper_runtime_decisions",
            "paper_observation_policy_reviews",
            "paper_eligibility_candidates",
            "orderbook_snapshots",
            "paper_sessions",
            "system_state",
            "service_health",
            "no_trade_log",
        ):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO system_state (
                current_mode, previous_mode, state_status, kill_switch_active,
                cooldown_active, attack_mode_active, reason, actor, metadata_json
            )
            VALUES (%s, NULL, 'ACTIVE', false, false, false, 'autopsy test', 'test', %s)
            """,
            (mode, Jsonb({"paper_simulation": {"enabled": mode == "PAPER"}})),
        )
        conn.execute(
            """
            INSERT INTO paper_sessions (
                paper_session_id, session_name, starting_balance,
                current_balance_snapshot, realized_pnl, unrealized_pnl,
                net_pnl, status, started_at, created_by, metadata_json
            )
            VALUES (%s,'Autopsy Session',1000,1000,0,0,0,'ACTIVE',now(),'test','{}'::jsonb)
            """,
            (SESSION_ID,),
        )


def seed_runtime_decision(
    *,
    decision_id: str,
    market_id: str,
    side: str,
    decision: str,
    score: float,
    blockers: list[str],
    thesis_state: str = "THESIS_SUPPORTED",
    exit_state: str = "EXIT_READY",
    edge_state: str = "EDGE_SUPPORTED",
) -> None:
    now = datetime.now(UTC)
    token_id = f"token-{market_id}-{side}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        if table_exists(conn, "orderbook_snapshots"):
            conn.execute(
                """
                INSERT INTO orderbook_snapshots (
                    orderbook_snapshot_id, market_id, token_id, side,
                    best_bid, best_ask, spread, mid_price, liquidity_score,
                    source, snapshot_status, is_stale, snapshot_at,
                    collected_at, created_at
                )
                VALUES (%s,%s,%s,%s,0.40,0.42,0.02,0.41,0.8,'test',
                        'OK',false,%s,%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (f"book-{decision_id}", market_id, token_id, side, now, now, now),
            )
        conn.execute(
            """
            INSERT INTO paper_runtime_decisions (
                decision_id, source_review_id, market_id, side, token_id,
                decision, paper_enter_allowed, edge_state, thesis_state,
                opportunity_score, risk_state, capital_state, exit_state,
                lifecycle_state, orderbook_state, token_verification_state,
                candidate_event_scope_state, lineage_state, blockers_json,
                warnings_json, required_to_pass_json, evidence, is_current_batch
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'RISK_OK','CAPITAL_SUPPORT',%s,
                    'DATA_ONLY_RESEARCH','FRESH','TOKENS_VERIFIED','CANDIDATE_SCOPED',
                    'COMPLETE',%s,'[]'::jsonb,%s,%s,true)
            """,
            (
                decision_id,
                f"review-{decision_id}",
                market_id,
                side,
                token_id,
                decision,
                decision == "ENTER" and not blockers,
                edge_state,
                thesis_state,
                score,
                exit_state,
                Jsonb(blockers),
                Jsonb(blockers),
                Jsonb({"paper_runtime_decision_id": decision_id, "orderbook_best_ask": 0.42, "orderbook_mid_price": 0.40}),
            ),
        )
        conn.execute(
            """
            INSERT INTO paper_observation_policy_reviews (
                paper_observation_policy_review_id, source_type, market_id,
                condition_id, side, token_id, observation_policy_state,
                decision_band, opportunity_score, edge_state, thesis_state,
                risk_state, capital_state, exit_state, lifecycle_state,
                orderbook_state, token_verification_state,
                candidate_event_scope_state, lineage_state,
                observation_allowed_by_policy, data_only,
                observation_policy_review_only, execution_allowed, paper_allowed,
                shadow_allowed, live_allowed, hard_blockers_json,
                soft_blockers_json, policy_blockers_json, required_to_pass_json,
                lineage_json, limits_json, metadata_json, policy_reason
            )
            VALUES (%s,'PROACTIVE_SEED_MESH',%s,%s,%s,%s,%s,'PAPER_OBSERVATION',
                    %s,%s,%s,'RISK_OK','CAPITAL_SUPPORT',%s,'DATA_ONLY_RESEARCH',
                    'FRESH','TOKENS_VERIFIED','CANDIDATE_SCOPED','COMPLETE',
                    %s,true,true,false,false,false,false,'[]'::jsonb,'[]'::jsonb,
                    %s,%s,%s,'{}'::jsonb,'{}'::jsonb,'test')
            """,
            (
                f"review-{decision_id}",
                market_id,
                f"condition-{market_id}",
                side,
                token_id,
                "OBSERVATION_POLICY_ELIGIBLE" if decision == "ENTER" and not blockers else "OBSERVATION_POLICY_WATCH",
                score,
                edge_state,
                thesis_state,
                exit_state,
                decision == "ENTER" and not blockers,
                Jsonb(blockers),
                Jsonb(blockers),
                Jsonb(blockers),
            ),
        )


def seed_enter_lifecycle(decision_id: str) -> None:
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count,
                signals_emitted_count, metadata_json, paper_session_id
            )
            VALUES ('11111111-1111-4111-8111-111111111111','PAPER_SIM',%s,%s,
                    'COMPLETED',1,1,1,1,'{}'::jsonb,%s)
            """,
            (now, now, SESSION_ID),
        )
        conn.execute(
            """
            INSERT INTO paper_signals (
                id, paper_run_id, market_id, signal_type, intended_outcome,
                trade_type, bucket_type, confidence, intended_price,
                intended_size, guard_result, reason_code, reason_text,
                payload_json, paper_session_id
            )
            VALUES ('22222222-2222-4222-8222-222222222222',
                    '11111111-1111-4111-8111-111111111111','m-enter',
                    'WOULD_ENTER','YES','PAPER_ENTRY','PAPER_INTENT',0.7,0.52,1,
                    'PASS','test','test','{}'::jsonb,%s)
            """,
            (SESSION_ID,),
        )
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, market_id, side, price_basis, intended_price,
                max_slippage, confidence, intent_status, intent_type,
                intent_reason, evidence, blockers, paper_only, live,
                execution_allowed, order_intent_created, generated_by,
                producer_name, is_runtime_generated, is_dry_run_generated,
                created_at, updated_at, paper_session_id
            )
            VALUES ('intent-enter','elig-enter','thesis','risk','exit','m-enter','YES',
                    'ORDERBOOK_MID',0.52,0.02,0.7,'CREATED','PAPER_ENTRY_INTENT',
                    'test',%s,'[]'::jsonb,true,false,false,false,'test','test',
                    true,false,%s,%s,%s)
            """,
            (Jsonb({"paper_runtime_decision_id": decision_id}), now, now, SESSION_ID),
        )
        conn.execute(
            """
            INSERT INTO paper_orders (
                id, paper_run_id, paper_signal_id, market_id, intended_outcome, action, intended_price,
                intended_size, notional, status, fill_ratio, filled_size,
                remaining_size, avg_fill_price, min_size_check_passed,
                payload_json, paper_session_id
            )
            VALUES ('33333333-3333-4333-8333-333333333333',
                    '11111111-1111-4111-8111-111111111111',
                    '22222222-2222-4222-8222-222222222222',
                    'm-enter','YES','BUY',
                    0.52,1,0.52,'FILLED',1,1,0,0.52,true,%s,%s)
            """,
            (Jsonb({"source_intent_id": "intent-enter"}), SESSION_ID),
        )
        conn.execute(
            """
            INSERT INTO paper_fills (
                paper_fill_id, paper_order_id, source_intent_id, market_id,
                side, fill_price, quantity, price_basis, metadata_json,
                paper_session_id
            )
            VALUES ('fill-enter','33333333-3333-4333-8333-333333333333','intent-enter',
                    'm-enter','YES',0.52,1,'TEST','{}'::jsonb,%s)
            """,
            (SESSION_ID,),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry, mark_price,
                unrealized, realized, current_status, thesis_state,
                invalidation_state, opened_at, updated_at, payload_json,
                paper_session_id
            )
            VALUES ('44444444-4444-4444-8444-444444444444',
                    '11111111-1111-4111-8111-111111111111','m-enter','YES',
                    1,0.52,0.52,0,0,'OPEN','ACTIVE','NONE',%s,%s,%s,%s)
            """,
            (now, now, Jsonb({"source_intent_id": "intent-enter"}), SESSION_ID),
        )


def seed_delta_run(*, paper_intents_before: int = 0, paper_intents_after: int = 1) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO candidate_eligibility_recovery_runs (
                run_id, cycle_id, system_power, status, paper_intents_before,
                paper_intents_after, paper_orders_delta, paper_fills_delta,
                paper_positions_delta, live_orders_delta, real_orders_delta,
                top_blockers_json, metadata_json
            )
            VALUES ('delta-run','delta-cycle','ON','OK',%s,%s,1,1,1,0,0,'[]'::jsonb,'{}'::jsonb)
            """,
            (paper_intents_before, paper_intents_after),
        )


def seed_degraded_service() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO service_health (
                service_name, service_type, status, last_heartbeat_at,
                last_error_at, error_count, details_json
            )
            VALUES ('paper_intent_gate','runtime','DEGRADED',now(),now(),1,%s)
            ON CONFLICT (service_name) DO UPDATE SET status='DEGRADED', last_error_at=now(), error_count=1, details_json=EXCLUDED.details_json, updated_at=now()
            """
            ,
            (Jsonb({"last_error": "test degraded"}),),
        )


def table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])
