from __future__ import annotations

import json

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def prepare_paper_eligibility_schema() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_eligibility_runs",
            "paper_eligibility_candidates",
            "exit_plan_rules",
            "exit_plan_runs",
            "exit_plans",
            "risk_decisions",
            "thesis_profile_evidence_items",
            "thesis_profiles",
            "signal_market_links",
            "neuron_signals",
            "coordinator_decision_inputs",
            "runtime_coordinator_decision_inputs",
            "coordinator_decisions",
            "brain_output_dependencies",
            "brain_outputs",
            "orderbook_snapshots",
            "markets_v2",
        ):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def seed_paper_eligibility_chain(
    suffix: str = "ok",
    *,
    exit_status: str = "COMPLETE",
    paper_exit_ready: bool = True,
    risk_approved: bool = True,
    thesis_status: str = "COMPLETE",
    market_id: str | None = "market-paper",
    side: str | None = "YES",
    orderbook: bool = True,
    binding: bool = True,
    lineage: bool = True,
    dry_run: bool = False,
) -> dict[str, str | None]:
    ids = {
        "market_id": market_id,
        "signal_id": f"signal-{suffix}",
        "brain_output_id": f"brain-{suffix}",
        "coordinator_decision_id": f"coord-{suffix}",
        "thesis_id": f"thesis-{suffix}",
        "risk_decision_id": f"risk-{suffix}",
        "exit_plan_id": f"exit-risk-{suffix}",
    }
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        orderbook_id = None
        if market_id:
            conn.execute("INSERT INTO markets_v2 (market_id, question, slug) VALUES (%s, 'Eligibility market?', %s) ON CONFLICT DO NOTHING", (market_id, market_id))
        if orderbook and market_id:
            orderbook_id = conn.execute(
                """
                INSERT INTO orderbook_snapshots (
                    orderbook_snapshot_id, market_id, best_bid, best_ask, spread,
                    mid_price, liquidity_score, source, snapshot_status, is_stale,
                    collected_at, created_at
                )
                VALUES (%s, %s, 0.45, 0.48, 0.03, 0.465, 0.8, 'test', 'OK', false, now(), now())
                RETURNING id
                """,
                (f"book-{suffix}", market_id),
            ).fetchone()["id"]
        if lineage and market_id:
            conn.execute(
                """
                INSERT INTO neuron_signals (
                    signal_id, neuron, event_type, source_name, market_id,
                    confidence, strength, evidence_json, status, raw_payload_ref,
                    correlation_id, created_at, updated_at
                )
                VALUES (%s, 'market', 'eligibility_test', 'runtime_source', %s, 0.8, 0.7, '{}'::jsonb, 'ACTIVE', %s, %s, now(), now())
                """,
                (ids["signal_id"], market_id, f"raw-{suffix}", f"corr-{suffix}"),
            )
            conn.execute(
                """
                INSERT INTO brain_outputs (
                    brain_output_id, brain, output_type, market_id, recommendation,
                    confidence, status, generated_by, metadata_json, created_at, updated_at
                )
                VALUES (%s, 'runtime_brain', 'paper_readiness', %s, 'WATCH', 0.8, 'READY', 'runtime', '{}'::jsonb, now(), now())
                """,
                (ids["brain_output_id"], market_id),
            )
            conn.execute(
                """
                INSERT INTO coordinator_decisions (
                    coordinator_decision_id, market_id, final_state, primary_reason,
                    confidence, governor_required, execution_allowed, status,
                    metadata_json, created_at, updated_at
                )
                VALUES (%s, %s, 'WATCH', 'eligibility fixture', 0.8, true, false, 'READY', %s::jsonb, now(), now())
                """,
                (
                    ids["coordinator_decision_id"],
                    market_id,
                    json.dumps({"generated_by": "runtime", "is_runtime_generated": True, "is_dry_run_generated": False}),
                ),
            )
        if binding and lineage and market_id:
            conn.execute(
                """
                INSERT INTO signal_market_links (
                    signal_id, market_id, link_type, link_status, confidence,
                    reason, created_by, link_confidence, link_reason,
                    link_evidence_json, link_method, linked_by,
                    is_auto_linked, is_review_required, is_runtime_link,
                    source_signal_id
                )
                VALUES (%s, %s, 'test', 'confirmed', 0.95, 'test', 'test', 0.95, 'test', '{}'::jsonb, 'explicit_market_id', 'test', true, false, true, %s)
                """,
                (ids["signal_id"], market_id, ids["signal_id"]),
            )
        conn.execute(
            """
            INSERT INTO thesis_profiles (
                thesis_id, market_id, side, status, thesis_type, why_now,
                expected_move, confidence, evidence, missing_evidence,
                invalidation_rules, risk_notes, source_coordinator_decision_id,
                source_brain_output_ids, source_signal_ids, orderbook_snapshot_id,
                generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, paper_candidate_allowed, risk_required,
                exit_required, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, 'RUNTIME_COORDINATOR_THESIS',
                'Eligibility test thesis.', 'YES', 0.8, '{}'::jsonb, '[]'::jsonb,
                '[]'::jsonb, '[]'::jsonb, %s, %s::jsonb, %s::jsonb, %s,
                %s, 'thesis_profile_builder', %s, %s, false, true, true, now(), now()
            )
            """,
            (
                ids["thesis_id"],
                market_id,
                side,
                thesis_status,
                ids["coordinator_decision_id"] if lineage else None,
                json.dumps([ids["brain_output_id"]] if lineage else []),
                json.dumps([ids["signal_id"]] if lineage else []),
                orderbook_id,
                "dry_run" if dry_run else "runtime",
                not dry_run,
                dry_run,
            ),
        )
        conn.execute(
            """
            INSERT INTO risk_decisions (
                risk_decision_id, thesis_id, market_id, decision, risk_status,
                risk_score, confidence, max_position_size, max_loss,
                market_risk_score, liquidity_risk_score, spread_risk_score,
                missing_data_risk_score, confidence_risk_score,
                daily_exposure_risk_score, risk_reasons, blockers, warnings,
                required_missing_evidence, source_thesis_status,
                orderbook_snapshot_id, paper_candidate_allowed,
                execution_allowed, risk_approved, exit_required,
                generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, 0.8, 10, 5,
                0.1, 0.1, 0.1, 0.0, 0.0, 0.0,
                '[]'::jsonb, %s::jsonb, '[]'::jsonb, '[]'::jsonb,
                %s, %s, false, false, %s, true,
                %s, 'risk_core', %s, %s, now(), now()
            )
            """,
            (
                ids["risk_decision_id"],
                ids["thesis_id"],
                market_id,
                "APPROVE" if risk_approved else "BLOCK",
                "LOW" if risk_approved else "BLOCKED",
                0.1 if risk_approved else 1.0,
                json.dumps([] if risk_approved else ["THESIS_BLOCKED"]),
                thesis_status,
                orderbook_id,
                risk_approved,
                "dry_run" if dry_run else "runtime",
                not dry_run,
                dry_run,
            ),
        )
        conn.execute(
            """
            INSERT INTO exit_plans (
                exit_plan_id, market_id, side, engine, risk_gate_run_id,
                entry_price, entry_size, target_exit, stop_loss, max_hold_seconds,
                invalidation_rule_json, liquidity_exit_check_json, emergency_exit_json,
                exit_mode, plan_status, created_from, data_confidence,
                insufficient_data, insufficient_data_reasons_json,
                thesis_id, risk_decision_ref, status, exit_type, invalidation_rules,
                emergency_exit_rules, liquidity_exit_check, time_exit_check,
                missing_exit_evidence, blockers, warnings, source_risk_status,
                source_risk_score, orderbook_snapshot_id, paper_intent_allowed,
                paper_exit_ready, execution_allowed, generated_by, producer_name,
                is_runtime_generated, is_dry_run_generated, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, 'EXIT_FOUNDATION', %s, 0, 0, 0.55, 0.42, 3600,
                '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, 'PAPER_SIM_EXIT',
                %s, 'exit_foundation', 0.85, false, '[]'::jsonb,
                %s, %s, %s, %s, '["THESIS_INVALIDATED"]'::jsonb,
                '["MANUAL_KILL"]'::jsonb, '{"max_spread":0.08}'::jsonb,
                '{"max_hold_seconds":3600}'::jsonb, %s::jsonb, %s::jsonb,
                '[]'::jsonb, %s, 0.1, %s, false, %s, false,
                'runtime', 'exit_foundation', true, false, now(), now()
            )
            """,
            (
                ids["exit_plan_id"],
                market_id,
                side,
                ids["risk_decision_id"],
                "ACTIVE" if exit_status == "COMPLETE" else "INSUFFICIENT_DATA",
                ids["thesis_id"],
                ids["risk_decision_id"],
                exit_status,
                "BASIC_PROTECTIVE_EXIT" if exit_status == "COMPLETE" else "BLOCKED_NO_ENTRY_EXIT",
                json.dumps([] if exit_status == "COMPLETE" else ["EXIT_NOT_READY"]),
                json.dumps([] if exit_status == "COMPLETE" else ["EXIT_NOT_READY"]),
                "LOW" if risk_approved else "BLOCKED",
                orderbook_id,
                paper_exit_ready,
            ),
        )
    return ids
