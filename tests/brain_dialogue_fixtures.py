from __future__ import annotations

from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.paper_eligibility import PaperEligibilityService
from app.services.system_power import SystemPowerService

from paper_eligibility_fixtures import seed_paper_eligibility_chain


def prepare_brain_dialogue() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "brain_dialogue_events",
            "fee_reward_signals",
            "fee_snapshots",
            "liquidity_signals",
            "liquidity_snapshots",
            "market_lifecycle_events",
            "market_technical_signals",
            "market_snapshots",
            "rules_analysis",
            "market_rules",
            "wording_risk_scores",
            "news_market_links",
            "news_normalized_events",
            "news_raw_events",
            "social_market_links",
            "social_normalized_events",
            "social_raw_events",
            "whale_events",
            "whale_scan_runs",
            "whale_market_scores",
            "ai_decision_logs",
            "ai_responses",
            "capital_brain_outputs",
            "capital_state_v2",
            "paper_capital_ledger",
            "paper_daily_pnl",
            "paper_exit_loop_runs",
            "paper_execution_runs",
            "paper_trade_ledger",
            "paper_fills",
            "paper_positions",
            "paper_orders",
            "paper_intent_runs",
            "no_trade_runs",
            "paper_intents",
            "no_trade_log",
            "candidate_eligibility_recovery_runs",
            "post_side_risk_exit_recovery_runs",
            "downstream_evidence_recompute_runs",
            "side_evidence_recovery_runs",
            "evidence_refresh_runs",
            "brain_mesh_activation_runs",
            "paper_eligibility_runs",
            "paper_eligibility_candidates",
            "exit_plan_rules",
            "exit_plan_runs",
            "exit_plans",
            "risk_decisions",
            "thesis_profile_evidence_items",
            "thesis_profiles",
            "signal_market_links",
            "neuron_signal_bindings",
            "neuron_signals",
            "coordinator_decisions",
            "brain_outputs",
            "orderbook_snapshots",
            "runtime_cycles_v2",
            "event_log",
            "service_health",
            "markets_v2",
        ):
            if conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]:
                conn.execute(f"DELETE FROM {table}")
    SystemPowerService().turn_on(actor="test", reason="brain_dialogue_prepare", correlation_id="brain-dialogue-on")


def seed_dialogue_sources() -> dict[str, str | None]:
    ids = seed_paper_eligibility_chain("dialogue")
    PaperEligibilityService().evaluate_candidates(limit=10)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (
                cycle_id, mode, status, scanner_started, scanner_finished,
                intelligence_started, intelligence_finished, paper_started, paper_finished,
                metadata_json
            )
            VALUES (
                'dialogue-cycle', 'DATA_ONLY', 'COMPLETED', true, true,
                true, true, true, true, '{"source":"test"}'::jsonb
            )
            """
        )
        conn.execute(
            """
            INSERT INTO event_log (
                event_id, event_type, aggregate_type, aggregate_id, source_service,
                correlation_id, cycle_id, occurred_at, payload_json, metadata_json
            )
            VALUES (
                'event-data-dialogue', 'market.snapshot.created', 'market', %s,
                'data_foundation', 'dialogue-cycle', 'dialogue-cycle', now(),
                %s::jsonb, '{}'::jsonb
            )
            """,
            (ids["market_id"], '{"market_id":"market-paper"}'),
        )
        conn.execute(
            """
            INSERT INTO brain_mesh_activation_runs (
                run_id, cycle_id, phase1_cycle_id, system_power, status,
                evidence_created, brain_outputs_created, coordinator_decisions_created,
                thesis_profiles_created, position_thesis_profiles_created
            )
            VALUES ('brain-dialogue-run', 'dialogue-cycle', 'phase1-dialogue', 'ON', 'OK', 2, 3, 4, 1, 1)
            """
        )
        conn.execute(
            """
            INSERT INTO evidence_refresh_runs (
                run_id, cycle_id, system_power, status, markets_checked,
                orderbook_snapshots_created, signals_checked, bindings_created,
                bindings_refreshed, bindings_rejected, sides_recovered
            )
            VALUES ('evidence-dialogue-run', 'dialogue-cycle', 'ON', 'OK', 3, 3, 5, 2, 1, 1, 2)
            """
        )
        conn.execute(
            """
            INSERT INTO side_evidence_recovery_runs (
                run_id, cycle_id, system_power, status, links_checked,
                candidates_checked, token_mappings_checked, sides_recovered, sides_rejected
            )
            VALUES ('side-dialogue-run', 'dialogue-cycle', 'ON', 'OK', 5, 5, 5, 2, 1)
            """
        )
        conn.execute(
            """
            INSERT INTO downstream_evidence_recompute_runs (
                run_id, cycle_id, system_power, status,
                thesis_checked, thesis_updated, risk_checked, risk_updated,
                exit_checked, exit_updated, eligibility_checked, eligibility_updated,
                no_trade_checked, no_trade_updated
            )
            VALUES ('downstream-dialogue-run', 'dialogue-cycle', 'ON', 'OK', 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
            """
        )
        conn.execute(
            """
            INSERT INTO post_side_risk_exit_recovery_runs (
                run_id, cycle_id, system_power, status, candidates_checked,
                candidates_with_side, risk_checked, risk_approved_before,
                risk_approved_after, exit_checked, exit_ready_before,
                exit_ready_after, eligible_before, eligible_after,
                paper_intents_before, paper_intents_after
            )
            VALUES ('post-side-dialogue-run', 'dialogue-cycle', 'ON', 'OK', 1, 1, 1, 0, 1, 1, 0, 1, 0, 1, 0, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO paper_intent_runs (
                run_id, status, candidates_checked, eligible_candidates,
                paper_intents_created, no_trade_records_created,
                paper_ready_before, paper_ready_after, orders_created,
                order_intents_created, fills_created, positions_created,
                live_actions_created
            )
            VALUES ('intent-dialogue-run', 'OK', 1, 1, 0, 0, false, false, 0, 0, 0, 0, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO paper_execution_runs (
                run_id, cycle_id, system_power, status, intents_checked,
                executable_intents, orders_created, fills_created,
                positions_created, blocked_intents, real_orders_delta, live_orders_delta
            )
            VALUES ('execution-dialogue-run', 'dialogue-cycle', 'ON', 'NO_VALID_PAPER_INTENTS', 0, 0, 0, 0, 0, 0, 0, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO paper_exit_loop_runs (
                run_id, system_power, status, open_positions_checked,
                closed_positions_count, marked_positions_count,
                blocked_positions_count, no_exit_price_count,
                no_exit_condition_count, orphan_positions_count
            )
            VALUES ('exit-loop-dialogue-run', 'ON', 'NO_OPEN_PAPER_POSITIONS', 0, 0, 0, 0, 0, 0, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO paper_daily_pnl (
                pnl_date, realized_pnl, unrealized_pnl, net_pnl,
                closed_trades_count, open_positions_count
            )
            VALUES (CURRENT_DATE, 0, 0, 0, 0, 0)
            ON CONFLICT (pnl_date) DO UPDATE SET updated_at = now()
            """
        )
    return ids


def seed_neuron_dialogue_sources(market_id: str = "market-neuron") -> dict[str, str]:
    orderbook_id = f"ob-{uuid4().hex}"
    liquidity_id = f"liq-{uuid4().hex}"
    fee_id = f"fee-{uuid4().hex}"
    rules_id = f"rules-{uuid4().hex}"
    news_id = f"news-{uuid4().hex}"
    social_id = f"social-{uuid4().hex}"
    whale_id = str(uuid4())
    whale_scan_id = str(uuid4())
    ai_id = f"ai-{uuid4().hex}"
    position_id = str(uuid4())
    paper_run_id = str(uuid4())
    cycle_id = str(uuid4())
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO cycles (
                id, started_at, status, mode, trigger_source, top_n,
                markets_fetched_count, markets_scored_count, markets_ranked_count,
                decisions_count, metadata, created_at, updated_at
            )
            VALUES (%s, now(), 'COMPLETED', 'SCAN_ONLY', 'test', 1, 1, 1, 1, 0, '{}'::jsonb, now(), now())
            """,
            (cycle_id,),
        )
        conn.execute(
            """
            INSERT INTO market_snapshots (
                cycle_id, market_id, question, captured_at, yes_price, no_price,
                best_bid, best_ask, spread, liquidity, volume_24h,
                time_to_close_seconds, created_at
            )
            VALUES (%s, %s, 'Will neuron tests pass?', now(), 0.42, 0.58, 0.41, 0.43, 0.02, 1200, 450, 7200, now())
            """,
            (cycle_id, market_id),
        )
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask,
                spread, mid_price, liquidity_score, snapshot_status, is_stale,
                collected_at, created_at
            )
            VALUES (%s, %s, 'token-yes', 'YES', 0.41, 0.43, 0.02, 0.42, 0.91, 'OK', false, now(), now())
            """,
            (orderbook_id, market_id),
        )
        conn.execute(
            """
            INSERT INTO liquidity_snapshots (
                liquidity_snapshot_id, market_id, orderbook_snapshot_id, liquidity_score,
                exit_quality, max_safe_size, fill_probability, snapshot_at
            )
            VALUES (%s, %s, %s, 0.88, 0.86, 50, 0.94, now())
            """,
            (liquidity_id, market_id, orderbook_id),
        )
        conn.execute(
            """
            INSERT INTO fee_snapshots (
                fee_snapshot_id, market_id, maker_fee, taker_fee, spread_cost,
                estimated_slippage_cost, net_edge_adjustment, snapshot_at
            )
            VALUES (%s, %s, 0.001, 0.002, 0.01, 0.003, -0.014, now())
            """,
            (fee_id, market_id),
        )
        conn.execute(
            """
            INSERT INTO rules_analysis (
                rules_analysis_id, market_id, wording_risk, dispute_risk,
                resolution_clarity, compliance_status, recommendation, created_at
            )
            VALUES (%s, %s, 0.12, 0.04, 0.93, 'CLEAR', 'TRADE_ALLOWED', now())
            """,
            (rules_id, market_id),
        )
        conn.execute(
            """
            INSERT INTO news_normalized_events (
                news_event_id, source_id, title, normalized_title, published_at,
                collected_at, importance_score, urgency_score, novelty_score,
                source_reliability, status, created_at
            )
            VALUES (%s, 'test-news', 'Neuron news event', 'neuron news event', now(), now(), 0.7, 0.3, 0.8, 0.9, 'NORMALIZED', now())
            """,
            (news_id,),
        )
        conn.execute(
            """
            INSERT INTO social_normalized_events (
                social_event_id, source_id, platform, author_handle, text,
                normalized_text,
                published_at, collected_at, engagement_score, influence_score,
                spam_score, bot_risk, novelty_score, status, created_at
            )
            VALUES (%s, 'test-social', 'test', 'operator', 'Neuron social event', 'neuron social event', now(), now(), 0.6, 0.5, 0.05, 0.04, 0.7, 'NORMALIZED', now())
            """,
            (social_id,),
        )
        conn.execute(
            """
            INSERT INTO whale_scan_runs (
                id, source_type, status, scanner_version, started_at, ended_at,
                input_count, success_count, failure_count, metadata_json,
                created_at, updated_at
            )
            VALUES (%s, 'test', 'COMPLETED', 'test', now(), now(), 1, 1, 0, '{}'::jsonb, now(), now())
            """,
            (whale_scan_id,),
        )
        conn.execute(
            """
            INSERT INTO whale_events (
                id, whale_scan_run_id, whale_event_id, market_id, wallet_address,
                event_timestamp, event_direction_class, side_or_outcome, size,
                notional, price, source_type, source_payload_json,
                detection_reason_code, detection_reason_text, created_at, side,
                action_type, size_usd, event_time, raw_event_json,
                normalized_event_json, confidence, metadata_json
            )
            VALUES (
                %s, %s, %s, %s, '0xabc',
                now(), 'ENTRY', 'YES', 10,
                4.2, 0.42, 'test', '{}'::jsonb,
                'TEST', 'fixture whale event', now(), 'YES',
                'BUY', 4.2, now(), '{}'::jsonb,
                '{}'::jsonb, 0.8, '{}'::jsonb
            )
            """,
            (whale_id, whale_scan_id, f"whale-{uuid4().hex}", market_id),
        )
        conn.execute(
            """
            INSERT INTO ai_decision_logs (
                ai_decision_id, market_id, correlation_id, task_type, decision_type,
                output_json, confidence, risk_flags_json, created_at
            )
            VALUES (%s, %s, 'neuron-ai', 'context', 'OBSERVE', '{}'::jsonb, 0.77, '[]'::jsonb, now())
            """,
            (ai_id, market_id),
        )
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, mode, started_at, ended_at, status, metadata_json
            )
            VALUES (%s, 'PAPER', now(), now(), 'COMPLETED', '{}'::jsonb)
            """,
            (paper_run_id,),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry, mark_price,
                unrealized, realized, current_status, thesis_state, invalidation_state, opened_at, updated_at,
                payload_json
            )
            VALUES (%s, %s, %s, 'YES', 10, 0.42, 0.44, 0.2, 0, 'OPEN', 'ACTIVE', 'NONE', now(), now(), '{}'::jsonb)
            """,
            (position_id, paper_run_id, market_id),
        )
    return {
        "market_id": market_id,
        "orderbook_id": orderbook_id,
        "position_id": position_id,
    }
