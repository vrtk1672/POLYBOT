from __future__ import annotations

import os
from pathlib import Path
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.config import ENV_FILE_STATUS, canonical_runtime_mode, get_settings
from app.db.connection import DatabaseConnectionFactory
from app.services.capital_allocator import LiveCapitalSource, PaperCapitalSource
from app.stage4 import get_stage4_settings
from app.runtime.health_truth import HealthTruthService
from app.repositories.event_store_repository import EventStoreRepository


class OperatorDashboardQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def get_kpi_quality(self, recent_cycles: int = 5, top_reasons_limit: int = 5) -> dict[str, object]:
        with self._factory.connect() as conn:
            runtime_cycles = conn.execute(
                """
                SELECT id, started_at, completed_at, status, mode, trigger_source,
                       markets_fetched_count, markets_scored_count, markets_ranked_count,
                       decisions_count, selected_market_id
                FROM cycles
                WHERE trigger_source = 'runtime.market_service'
                ORDER BY started_at DESC, id DESC
                LIMIT %s
                """,
                (recent_cycles,),
            ).fetchall()
            if not runtime_cycles:
                return {
                    "window": {
                        "recent_cycle_count": 0,
                        "window_started_at": None,
                        "window_completed_at": None,
                        "cycle_ids": [],
                    },
                    "kpis": {
                        "opportunity_intake": {
                            "opportunities_seen": 0,
                            "opportunities_scored": 0,
                            "candidates_ranked": 0,
                            "ranking_policy_candidates": 0,
                            "ranking_policy_selectable": 0,
                            "ranking_policy_rejected": 0,
                            "paper_candidates_selected": 0,
                        },
                        "paper_activity": {
                            "paper_signals_created": 0,
                            "paper_would_enter": 0,
                            "paper_would_block": 0,
                            "paper_orders_created": 0,
                            "paper_orders_filled": 0,
                            "paper_positions_opened": 0,
                            "paper_positions_closed": 0,
                            "paper_position_events_count": 0,
                        },
                        "shadow_activity": {
                            "shadow_orders_created": 0,
                            "shadow_would_submit": 0,
                            "shadow_would_reject": 0,
                            "shadow_blocked_by_risk": 0,
                            "shadow_blocked_by_config": 0,
                            "shadow_invalid_request": 0,
                            "shadow_positions_pending": 0,
                        },
                        "invalidation_advisory_activity": {
                            "invalidation_policy_records_count": 0,
                            "exit_advisory_records_count": 0,
                            "advisory_resolution_records_count": 0,
                            "command_intent_records_count": 0,
                        },
                        "flow_ratios": {
                            "selection_rate": None,
                            "reject_rate": None,
                            "paper_order_per_signal_rate": None,
                            "fill_rate": None,
                            "position_open_rate": None,
                            "exit_advisory_incidence_rate": None,
                        },
                    },
                    "quality": {
                        "ranking_tier_distribution": [],
                        "ranking_gate_distribution": [],
                        "trade_classification_distribution": [],
                        "bucket_allocation_distribution": [],
                        "invalidation_state_distribution": [],
                        "exit_policy_distribution": [],
                        "advisory_action_distribution": [],
                        "command_intent_distribution": [],
                        "paper_signal_distribution": [],
                        "paper_position_status_distribution": [],
                        "shadow_status_distribution": [],
                        "top_shadow_reason_codes": [],
                        "top_rejection_reasons": [],
                        "top_paper_block_reasons": [],
                        "top_rank_reasons": [],
                        "top_advisory_reasons": [],
                    },
                    "observations": [
                        "No persisted runtime.market_service cycles are available yet, so KPI and decision-quality metrics are not available."
                    ],
                }

            cycle_ids = [str(row["id"]) for row in runtime_cycles]
            window_started_at = min((row["started_at"] for row in runtime_cycles if row["started_at"] is not None), default=None)
            window_completed_at = max(
                ((row["completed_at"] or row["started_at"]) for row in runtime_cycles if row["started_at"] is not None),
                default=None,
            )

            intake = conn.execute(
                """
                SELECT
                    COALESCE(SUM(markets_fetched_count), 0) AS opportunities_seen,
                    COALESCE(SUM(markets_scored_count), 0) AS opportunities_scored,
                    COALESCE(SUM(markets_ranked_count), 0) AS candidates_ranked
                FROM cycles
                WHERE id = ANY(%s)
                """,
                (cycle_ids,),
            ).fetchone()
            ranking_policy_counts = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_candidates,
                    COUNT(*) FILTER (WHERE gate_decision_class = 'SELECTABLE') AS selectable_candidates,
                    COUNT(*) FILTER (WHERE gate_decision_class IN ('BLOCKED', 'HARD_REJECT')) AS rejected_candidates
                FROM ranking_policy_candidates rpc
                JOIN ranking_policy_runs rpr ON rpr.id = rpc.ranking_policy_run_id
                WHERE rpr.source_ref = ANY(%s)
                """,
                (cycle_ids,),
            ).fetchone()
            paper_run_counts = conn.execute(
                """
                SELECT
                    COALESCE(SUM(candidates_selected_count), 0) AS selected_candidates,
                    COALESCE(SUM(signals_emitted_count), 0) AS signals_emitted
                FROM paper_runs
                WHERE cycle_id = ANY(%s)
                """,
                (cycle_ids,),
            ).fetchone()
            paper_signal_counts = conn.execute(
                """
                SELECT
                    COUNT(*) AS signals_created,
                    COUNT(*) FILTER (WHERE signal_type = 'WOULD_ENTER') AS would_enter_count,
                    COUNT(*) FILTER (WHERE signal_type = 'WOULD_BLOCK') AS would_block_count
                FROM paper_signals
                WHERE cycle_id = ANY(%s)
                """,
                (cycle_ids,),
            ).fetchone()
            paper_order_counts = conn.execute(
                """
                SELECT
                    COUNT(*) AS orders_created,
                    COUNT(*) FILTER (WHERE po.status = 'FILLED') AS orders_filled
                FROM paper_orders po
                JOIN paper_runs pr ON pr.id = po.paper_run_id
                WHERE pr.cycle_id = ANY(%s)
                """,
                (cycle_ids,),
            ).fetchone()
            paper_position_counts = conn.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE opened_at >= %s) AS positions_opened,
                    COUNT(*) FILTER (WHERE closed_at IS NOT NULL AND closed_at >= %s) AS positions_closed
                FROM paper_positions
                """,
                (window_started_at, window_started_at),
            ).fetchone()
            paper_position_events_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM paper_position_events
                WHERE event_at >= %s
                """,
                (window_started_at,),
            ).fetchone()["count"]
            shadow_order_counts = conn.execute(
                """
                SELECT
                    COUNT(*) AS orders_created,
                    COUNT(*) FILTER (WHERE status = 'WOULD_SUBMIT') AS would_submit_count,
                    COUNT(*) FILTER (WHERE status = 'WOULD_REJECT') AS would_reject_count,
                    COUNT(*) FILTER (WHERE status = 'BLOCKED_BY_RISK') AS blocked_by_risk_count,
                    COUNT(*) FILTER (WHERE status = 'BLOCKED_BY_CONFIG') AS blocked_by_config_count,
                    COUNT(*) FILTER (WHERE status = 'INVALID_REQUEST') AS invalid_request_count
                FROM shadow_orders
                WHERE cycle_id = ANY(%s)
                """,
                (cycle_ids,),
            ).fetchone()
            shadow_position_counts = conn.execute(
                """
                SELECT COUNT(*) FILTER (WHERE current_status = 'PENDING_SUBMISSION') AS pending_positions
                FROM shadow_positions
                WHERE updated_at >= %s
                """,
                (window_started_at,),
            ).fetchone()
            invalidation_counts = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM invalidation_policy_records
                WHERE cycle_id = ANY(%s)
                """,
                (cycle_ids,),
            ).fetchone()["count"]
            exit_advisory_counts = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM exit_advisory_records ear
                JOIN exit_advisory_runs earun ON earun.id = ear.exit_advisory_run_id
                WHERE earun.source_ref = ANY(%s)
                """,
                (cycle_ids,),
            ).fetchone()["count"]
            advisory_resolution_counts = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM advisory_resolution_records arr
                WHERE arr.cycle_id = ANY(%s)
                """,
                (cycle_ids,),
            ).fetchone()["count"]
            command_intent_counts = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM command_intent_records cir
                JOIN command_intent_runs cirun ON cirun.id = cir.command_intent_run_id
                WHERE cirun.source_ref = ANY(%s)
                """,
                (cycle_ids,),
            ).fetchone()["count"]

            ranking_tiers = conn.execute(
                """
                SELECT rank_tier_class AS label, COUNT(*) AS count
                FROM ranking_policy_candidates rpc
                JOIN ranking_policy_runs rpr ON rpr.id = rpc.ranking_policy_run_id
                WHERE rpr.source_ref = ANY(%s)
                GROUP BY rank_tier_class
                ORDER BY count DESC, rank_tier_class ASC
                """,
                (cycle_ids,),
            ).fetchall()
            ranking_gates = conn.execute(
                """
                SELECT gate_decision_class AS label, COUNT(*) AS count
                FROM ranking_policy_candidates rpc
                JOIN ranking_policy_runs rpr ON rpr.id = rpc.ranking_policy_run_id
                WHERE rpr.source_ref = ANY(%s)
                GROUP BY gate_decision_class
                ORDER BY count DESC, gate_decision_class ASC
                """,
                (cycle_ids,),
            ).fetchall()
            trade_distribution = conn.execute(
                """
                SELECT primary_trade_type AS label, COUNT(*) AS count
                FROM trade_classifications
                WHERE cycle_id = ANY(%s)
                GROUP BY primary_trade_type
                ORDER BY count DESC, primary_trade_type ASC
                """,
                (cycle_ids,),
            ).fetchall()
            bucket_distribution = conn.execute(
                """
                SELECT assigned_bucket_class AS label, COUNT(*) AS count
                FROM bucket_allocations ba
                JOIN bucket_allocation_runs bar ON bar.id = ba.bucket_allocation_run_id
                WHERE bar.source_ref = ANY(%s)
                GROUP BY assigned_bucket_class
                ORDER BY count DESC, assigned_bucket_class ASC
                """,
                (cycle_ids,),
            ).fetchall()
            invalidation_distribution = conn.execute(
                """
                SELECT invalidation_state_class AS label, COUNT(*) AS count
                FROM invalidation_policy_records
                WHERE cycle_id = ANY(%s)
                GROUP BY invalidation_state_class
                ORDER BY count DESC, invalidation_state_class ASC
                """,
                (cycle_ids,),
            ).fetchall()
            exit_policy_distribution = conn.execute(
                """
                SELECT exit_policy_class AS label, COUNT(*) AS count
                FROM invalidation_policy_records
                WHERE cycle_id = ANY(%s)
                GROUP BY exit_policy_class
                ORDER BY count DESC, exit_policy_class ASC
                """,
                (cycle_ids,),
            ).fetchall()
            advisory_distribution = conn.execute(
                """
                SELECT advisory_action_class AS label, COUNT(*) AS count
                FROM exit_advisory_records ear
                JOIN exit_advisory_runs earun ON earun.id = ear.exit_advisory_run_id
                WHERE earun.source_ref = ANY(%s)
                GROUP BY advisory_action_class
                ORDER BY count DESC, advisory_action_class ASC
                """,
                (cycle_ids,),
            ).fetchall()
            command_distribution = conn.execute(
                """
                SELECT command_intent_class AS label, COUNT(*) AS count
                FROM command_intent_records cir
                JOIN command_intent_runs cirun ON cirun.id = cir.command_intent_run_id
                WHERE cirun.source_ref = ANY(%s)
                GROUP BY command_intent_class
                ORDER BY count DESC, command_intent_class ASC
                """,
                (cycle_ids,),
            ).fetchall()
            paper_signal_distribution = conn.execute(
                """
                SELECT signal_type AS label, COUNT(*) AS count
                FROM paper_signals
                WHERE cycle_id = ANY(%s)
                GROUP BY signal_type
                ORDER BY count DESC, signal_type ASC
                """,
                (cycle_ids,),
            ).fetchall()
            paper_position_status_distribution = conn.execute(
                """
                SELECT current_status AS label, COUNT(*) AS count
                FROM paper_positions
                WHERE updated_at >= %s
                GROUP BY current_status
                ORDER BY count DESC, current_status ASC
                """,
                (window_started_at,),
            ).fetchall()
            shadow_status_distribution = conn.execute(
                """
                SELECT status AS label, COUNT(*) AS count
                FROM shadow_orders
                WHERE cycle_id = ANY(%s)
                GROUP BY status
                ORDER BY count DESC, status ASC
                """,
                (cycle_ids,),
            ).fetchall()
            shadow_reason_codes = conn.execute(
                """
                SELECT reason_code AS label, COUNT(*) AS count
                FROM shadow_order_events
                WHERE event_at >= %s
                GROUP BY reason_code
                ORDER BY count DESC, reason_code ASC
                LIMIT %s
                """,
                (window_started_at, top_reasons_limit),
            ).fetchall()
            rejection_reasons = conn.execute(
                """
                SELECT reason_code AS label, COUNT(*) AS count
                FROM rejection_ledger
                WHERE cycle_id = ANY(%s)
                GROUP BY reason_code
                ORDER BY count DESC, reason_code ASC
                LIMIT %s
                """,
                (cycle_ids, top_reasons_limit),
            ).fetchall()
            paper_block_reasons = conn.execute(
                """
                SELECT reason_code AS label, COUNT(*) AS count
                FROM paper_signals
                WHERE cycle_id = ANY(%s)
                  AND signal_type = 'WOULD_BLOCK'
                GROUP BY reason_code
                ORDER BY count DESC, reason_code ASC
                LIMIT %s
                """,
                (cycle_ids, top_reasons_limit),
            ).fetchall()
            rank_reasons = conn.execute(
                """
                SELECT selection_reason_text AS label, COUNT(*) AS count
                FROM ranking_policy_candidates rpc
                JOIN ranking_policy_runs rpr ON rpr.id = rpc.ranking_policy_run_id
                WHERE rpr.source_ref = ANY(%s)
                GROUP BY selection_reason_text
                ORDER BY count DESC, selection_reason_text ASC
                LIMIT %s
                """,
                (cycle_ids, top_reasons_limit),
            ).fetchall()
            advisory_reasons = conn.execute(
                """
                SELECT advisory_reason_text AS label, COUNT(*) AS count
                FROM exit_advisory_records ear
                JOIN exit_advisory_runs earun ON earun.id = ear.exit_advisory_run_id
                WHERE earun.source_ref = ANY(%s)
                GROUP BY advisory_reason_text
                ORDER BY count DESC, advisory_reason_text ASC
                LIMIT %s
                """,
                (cycle_ids, top_reasons_limit),
            ).fetchall()

        opportunity_intake = {
            "opportunities_seen": int(intake["opportunities_seen"]),
            "opportunities_scored": int(intake["opportunities_scored"]),
            "candidates_ranked": int(intake["candidates_ranked"]),
            "ranking_policy_candidates": int(ranking_policy_counts["total_candidates"]),
            "ranking_policy_selectable": int(ranking_policy_counts["selectable_candidates"]),
            "ranking_policy_rejected": int(ranking_policy_counts["rejected_candidates"]),
            "paper_candidates_selected": int(paper_run_counts["selected_candidates"]),
        }
        paper_activity = {
            "paper_signals_created": int(paper_signal_counts["signals_created"]),
            "paper_would_enter": int(paper_signal_counts["would_enter_count"]),
            "paper_would_block": int(paper_signal_counts["would_block_count"]),
            "paper_orders_created": int(paper_order_counts["orders_created"]),
            "paper_orders_filled": int(paper_order_counts["orders_filled"]),
            "paper_positions_opened": int(paper_position_counts["positions_opened"]),
            "paper_positions_closed": int(paper_position_counts["positions_closed"]),
            "paper_position_events_count": int(paper_position_events_count),
        }
        shadow_activity = {
            "shadow_orders_created": int(shadow_order_counts["orders_created"]),
            "shadow_would_submit": int(shadow_order_counts["would_submit_count"]),
            "shadow_would_reject": int(shadow_order_counts["would_reject_count"]),
            "shadow_blocked_by_risk": int(shadow_order_counts["blocked_by_risk_count"]),
            "shadow_blocked_by_config": int(shadow_order_counts["blocked_by_config_count"]),
            "shadow_invalid_request": int(shadow_order_counts["invalid_request_count"]),
            "shadow_positions_pending": int(shadow_position_counts["pending_positions"] or 0),
        }
        invalidation_advisory_activity = {
            "invalidation_policy_records_count": int(invalidation_counts),
            "exit_advisory_records_count": int(exit_advisory_counts),
            "advisory_resolution_records_count": int(advisory_resolution_counts),
            "command_intent_records_count": int(command_intent_counts),
        }
        flow_ratios = {
            "selection_rate": _safe_ratio(opportunity_intake["paper_candidates_selected"], opportunity_intake["candidates_ranked"]),
            "reject_rate": _safe_ratio(opportunity_intake["ranking_policy_rejected"], opportunity_intake["ranking_policy_candidates"]),
            "paper_order_per_signal_rate": _safe_ratio(paper_activity["paper_orders_created"], paper_activity["paper_signals_created"]),
            "fill_rate": _safe_ratio(paper_activity["paper_orders_filled"], paper_activity["paper_orders_created"]),
            "position_open_rate": _safe_ratio(paper_activity["paper_positions_opened"], paper_activity["paper_orders_filled"]),
            "exit_advisory_incidence_rate": _safe_ratio(
                invalidation_advisory_activity["exit_advisory_records_count"],
                invalidation_advisory_activity["invalidation_policy_records_count"],
            ),
        }

        observations: list[str] = [
            f"Recent runtime window covers {len(cycle_ids)} canonical refresh cycles from {window_started_at.isoformat() if window_started_at else 'n/a'} to {window_completed_at.isoformat() if window_completed_at else 'n/a'}.",
            f"Opportunity intake saw {opportunity_intake['opportunities_seen']} markets fetched, {opportunity_intake['candidates_ranked']} runtime-ranked candidates, and {paper_activity['paper_signals_created']} persisted paper signals.",
            f"Paper flow converted {paper_activity['paper_orders_created']} paper orders into {paper_activity['paper_orders_filled']} fills and {paper_activity['paper_positions_opened']} opened positions in the measured window.",
        ]
        if paper_activity["paper_would_block"] > paper_activity["paper_would_enter"] and paper_block_reasons:
            observations.append(
                f"Paper flow is currently more selective than active: {paper_activity['paper_would_block']} blocked signals vs {paper_activity['paper_would_enter']} would-enter signals, led by {paper_block_reasons[0]['label']}."
            )
        if opportunity_intake["ranking_policy_selectable"] == 0 and paper_activity["paper_would_enter"] > 0:
            observations.append(
                "Ranking policy produced no SELECTABLE candidates in the recent window while the paper signal layer still emitted WOULD_ENTER candidates, so policy and execution selection strictness are materially different."
            )

        return {
            "window": {
                "recent_cycle_count": len(cycle_ids),
                "window_started_at": window_started_at.isoformat() if window_started_at else None,
                "window_completed_at": window_completed_at.isoformat() if window_completed_at else None,
                "cycle_ids": cycle_ids,
            },
            "kpis": {
                "opportunity_intake": opportunity_intake,
                "paper_activity": paper_activity,
                "shadow_activity": shadow_activity,
                "invalidation_advisory_activity": invalidation_advisory_activity,
                "flow_ratios": flow_ratios,
            },
            "quality": {
                "ranking_tier_distribution": [_row_dict(row) for row in ranking_tiers],
                "ranking_gate_distribution": [_row_dict(row) for row in ranking_gates],
                "trade_classification_distribution": [_row_dict(row) for row in trade_distribution],
                "bucket_allocation_distribution": [_row_dict(row) for row in bucket_distribution],
                "invalidation_state_distribution": [_row_dict(row) for row in invalidation_distribution],
                "exit_policy_distribution": [_row_dict(row) for row in exit_policy_distribution],
                "advisory_action_distribution": [_row_dict(row) for row in advisory_distribution],
                "command_intent_distribution": [_row_dict(row) for row in command_distribution],
                "paper_signal_distribution": [_row_dict(row) for row in paper_signal_distribution],
                "paper_position_status_distribution": [_row_dict(row) for row in paper_position_status_distribution],
                "shadow_status_distribution": [_row_dict(row) for row in shadow_status_distribution],
                "top_shadow_reason_codes": [_row_dict(row) for row in shadow_reason_codes],
                "top_rejection_reasons": [_row_dict(row) for row in rejection_reasons],
                "top_paper_block_reasons": [_row_dict(row) for row in paper_block_reasons],
                "top_rank_reasons": [_row_dict(row) for row in rank_reasons],
                "top_advisory_reasons": [_row_dict(row) for row in advisory_reasons],
            },
            "observations": observations,
        }

    def get_system_health(self) -> dict[str, object]:
        app_settings = get_settings()
        stage4_settings = get_stage4_settings()
        paper_capital_source = PaperCapitalSource(connection_factory=self._factory, stage4_settings=stage4_settings)
        live_capital_source = LiveCapitalSource(stage4_settings=stage4_settings)
        paper_capital = paper_capital_source.snapshot()
        live_capital = live_capital_source.snapshot()
        with self._factory.connect() as conn:
            db_connected = conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
            cycle = conn.execute("SELECT * FROM cycles ORDER BY started_at DESC, id DESC LIMIT 1").fetchone()
            market_snapshot = conn.execute(
                """
                SELECT market_id, captured_at, created_at
                FROM market_snapshots
                ORDER BY captured_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            ranking_run = conn.execute(
                "SELECT id, status, started_at, ended_at FROM ranking_policy_runs ORDER BY started_at DESC, id DESC LIMIT 1"
            ).fetchone()
            invalidation_run = conn.execute(
                "SELECT id, status, started_at, ended_at FROM invalidation_policy_runs ORDER BY started_at DESC, id DESC LIMIT 1"
            ).fetchone()
            orchestration_run = conn.execute(
                "SELECT id, status, started_at, ended_at FROM orchestration_gate_runs ORDER BY started_at DESC, id DESC LIMIT 1"
            ).fetchone()
            pending_eligible = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM command_intent_records
                WHERE command_status_class = 'STAGED'
                  AND orchestration_eligibility_class = 'ELIGIBLE_FOR_CONTROLLED_ORCHESTRATION'
                """
            ).fetchone()["count"]
            critical_alerts = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM alert_events
                WHERE severity_class = 'CRITICAL'
                  AND created_at >= now() - interval '24 hours'
                """
            ).fetchone()["count"]
            live_open_positions = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM positions
                WHERE closed_at IS NULL
                """
            ).fetchone()["count"]
            live_active_orders = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM live_orders
                WHERE status = ANY(%s)
                """,
                (["SUBMISSION_REQUESTED", "SUBMITTED", "LIVE", "OPEN", "PARTIALLY_FILLED"],),
            ).fetchone()["count"]
            paper_open_positions = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM paper_positions
                WHERE closed_at IS NULL
                  AND current_status = ANY(%s)
                """,
                (["OPEN", "EXIT_PENDING"],),
            ).fetchone()["count"]
            paper_active_orders = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM paper_orders
                WHERE status = ANY(%s)
                """,
                (["CREATED", "OPEN", "PARTIALLY_FILLED"],),
            ).fetchone()["count"]
            daily_realized_loss = conn.execute(
                """
                SELECT COALESCE(ABS(SUM(LEAST(realized, 0))), 0) AS loss
                FROM positions
                WHERE updated_at >= date_trunc('day', now())
                """
            ).fetchone()["loss"]
            live_control = conn.execute(
                """
                SELECT action_class, status_class, reason_text, created_at
                FROM operator_control_actions
                WHERE action_class IN ('KILL', 'RESUME')
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            latest_news_run = conn.execute(
                """
                SELECT runs.started_at, runs.ended_at, runs.status, sources.source_key, sources.source_name
                FROM intelligence_ingestion_runs runs
                LEFT JOIN intelligence_sources sources ON sources.id = runs.intelligence_source_id
                ORDER BY runs.started_at DESC, runs.id DESC
                LIMIT 1
                """
            ).fetchone()
            latest_whale_scoring_run = conn.execute(
                """
                SELECT started_at, ended_at, status
                FROM whale_scoring_runs
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            latest_ai_digest = conn.execute(
                """
                SELECT created_at, title, source_ref
                FROM alert_events
                WHERE event_class = 'AI_INTELLIGENCE_DIGEST'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()

        warnings: list[str] = []
        now = datetime.now(UTC)
        if cycle is None:
            warnings.append("No persisted cycle history is available yet.")
        else:
            started_at = cycle["started_at"]
            if started_at is not None and now - started_at > timedelta(minutes=20):
                warnings.append("Last persisted cycle is older than 20 minutes.")
            if str(cycle["status"]) in {"FAILED", "PARTIAL"}:
                warnings.append(f"Last cycle status is {cycle['status']}.")
        if market_snapshot is None:
            warnings.append("No persisted market snapshots are available yet.")
        elif market_snapshot["captured_at"] is not None and now - market_snapshot["captured_at"] > timedelta(minutes=20):
            warnings.append("Market snapshot freshness is older than 20 minutes.")
        if invalidation_run is not None and str(invalidation_run["status"]) in {"FAILED", "COMPLETED_WITH_ERRORS"}:
            warnings.append(f"Latest invalidation policy run is {invalidation_run['status']}.")
        if orchestration_run is not None and str(orchestration_run["status"]) in {"FAILED", "COMPLETED_WITH_ERRORS"}:
            warnings.append(f"Latest orchestration gate run is {orchestration_run['status']}.")
        if critical_alerts:
            warnings.append(f"There are {critical_alerts} critical alert events in the last 24 hours.")
        if stage4_settings.live_kill_switch:
            warnings.append("LIVE_KILL_SWITCH is enabled.")
        if (
            live_control is not None
            and str(live_control["action_class"]) == "KILL"
            and str(live_control["status_class"]) == "ACTIVE_GUARD"
        ):
            warnings.append("Operator KILL guard is active for live submissions.")
        if latest_news_run is None:
            warnings.append("Always-on news ingestion has not persisted any runtime news runs yet.")

        return {
            "db_connected": db_connected,
            "runtime_mode": os.getenv("POLYBOT_RUNTIME_MODE", "paper"),
            "execution_mode": canonical_runtime_mode(os.getenv("POLYBOT_RUNTIME_MODE")),
            "execution_backend": os.getenv("POLYBOT_EXECUTION_BACKEND") or os.getenv("EXECUTION_BACKEND") or "paper",
            "env_runtime": {
                "env_file_exists": ENV_FILE_STATUS.exists,
                "env_file_loaded": ENV_FILE_STATUS.loaded,
                "env_file_path": ENV_FILE_STATUS.path,
                "env_example_exists": (Path(ENV_FILE_STATUS.path).with_name(".env.example")).exists(),
                "anthropic_api_key_present": bool(os.getenv("ANTHROPIC_API_KEY")),
                "ai_enabled_by_config": bool(app_settings.intelligence_ai_enabled),
                "ai_runtime_status": (
                    "DISABLED"
                    if not app_settings.intelligence_ai_enabled
                    else "ENABLED_KEY_PRESENT"
                    if os.getenv("ANTHROPIC_API_KEY")
                    else "ENABLED_KEY_MISSING"
                ),
                "live_trading_enabled": stage4_settings.live_trading_enabled,
                "live_kill_switch": stage4_settings.live_kill_switch,
            },
            "last_cycle": _row_dict(cycle),
            "last_market_snapshot": _row_dict(market_snapshot),
            "last_ranking_policy_run": _row_dict(ranking_run),
            "last_invalidation_policy_run": _row_dict(invalidation_run),
            "last_orchestration_gate_run": _row_dict(orchestration_run),
            "pending_eligible_command_intents": pending_eligible,
            "critical_alert_count_24h": critical_alerts,
            "live_cage": {
                "live_trading_enabled": stage4_settings.live_trading_enabled,
                "live_kill_switch": stage4_settings.live_kill_switch,
                "live_market_whitelist": list(stage4_settings.live_market_whitelist),
                "live_max_order_usd": stage4_settings.live_max_order_usd,
                "live_max_daily_loss_usd": stage4_settings.live_max_daily_loss_usd,
                "live_max_open_positions": stage4_settings.live_max_open_positions,
                "live_max_same_market_exposure": stage4_settings.live_max_same_market_exposure,
                "live_allow_scaling": stage4_settings.live_allow_scaling,
                "live_open_positions": int(live_open_positions),
                "live_active_orders": int(live_active_orders),
                "daily_realized_loss_usd": float(daily_realized_loss),
                "operator_control": _row_dict(live_control),
            },
            "paper_safe_policy": {
                "paper_safe_max_open_positions": stage4_settings.paper_safe_max_open_positions,
                "paper_max_same_market_exposure": stage4_settings.live_max_same_market_exposure,
                "paper_allow_scaling": stage4_settings.live_allow_scaling,
                "paper_open_positions": int(paper_open_positions),
                "paper_active_orders": int(paper_active_orders),
            },
            "paper_capital": {
                **paper_capital.to_payload(),
                "effective_max_alloc_per_trade_usd": paper_capital.metadata.get("max_alloc_per_trade_usd"),
                "effective_max_total_deployment_usd": paper_capital.metadata.get("max_total_deployment_usd"),
                "effective_reserve_target_usd": paper_capital.metadata.get("reserve_target_usd"),
            },
            "paper_capital_policy": {
                "paper_starting_capital_usd": stage4_settings.paper_starting_capital_usd,
                "paper_min_cash_reserve_pct": stage4_settings.paper_min_cash_reserve_pct,
                "paper_max_alloc_per_trade_pct": stage4_settings.paper_max_alloc_per_trade_pct,
                "paper_max_total_deployment_pct": stage4_settings.paper_max_total_deployment_pct,
            },
            "live_capital_source": {
                **live_capital.to_payload(),
                "balance_source": live_capital.metadata.get("balance_source"),
            },
            "intelligence_runtime": {
                "news_refresh_interval_seconds": app_settings.intelligence_refresh_interval_seconds,
                "whale_refresh_interval_seconds": app_settings.intelligence_whale_refresh_interval_seconds,
                "ai_enabled": bool(app_settings.intelligence_ai_enabled and os.getenv("ANTHROPIC_API_KEY")),
                "latest_news_run": _row_dict(latest_news_run),
                "latest_news_freshness": _freshness_status(
                    latest_news_run["ended_at"] if latest_news_run is not None else None,
                    stale_after_seconds=app_settings.intelligence_news_stale_after_seconds,
                ),
                "latest_whale_scoring_run": _row_dict(latest_whale_scoring_run),
                "latest_whale_freshness": _freshness_status(
                    latest_whale_scoring_run["ended_at"] if latest_whale_scoring_run is not None else None,
                    stale_after_seconds=app_settings.intelligence_whale_stale_after_seconds,
                ),
                "latest_ai_digest": _row_dict(latest_ai_digest),
                "latest_ai_freshness": _freshness_status(
                    latest_ai_digest["created_at"] if latest_ai_digest is not None else None,
                    stale_after_seconds=app_settings.intelligence_ai_stale_after_seconds,
                ),
            },
            "warnings": warnings,
        }

    def get_ranking_overview(self, limit: int = 10) -> dict[str, object]:
        with self._factory.connect() as conn:
            latest_policy_run = conn.execute(
                "SELECT id, status, started_at, ended_at FROM ranking_policy_runs ORDER BY started_at DESC, id DESC LIMIT 1"
            ).fetchone()
            top_ranked = conn.execute(
                """
                SELECT market_id, total_rank_score, rank_position, rank_tier_class,
                       gate_decision_class, gate_priority_class, selection_reason_text, created_at
                FROM ranking_policy_candidates
                ORDER BY created_at DESC, rank_position ASC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            recent_candidates = conn.execute(
                """
                SELECT market_id, total_rank_score, rank_position, rank_tier_class,
                       gate_decision_class, selection_reason_text, created_at
                FROM ranking_policy_candidates
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            selected_count = conn.execute(
                "SELECT COUNT(*) AS count FROM ranking_policy_candidates WHERE gate_decision_class = 'SELECTABLE'"
            ).fetchone()["count"]
            rejected = conn.execute(
                """
                SELECT market_id, gate_decision_class, selection_reason_text, created_at
                FROM ranking_policy_candidates
                WHERE gate_decision_class IN ('BLOCKED', 'HARD_REJECT')
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            rejection_ledger = conn.execute(
                """
                SELECT market_id, stage, reason_code, reason_text, created_at
                FROM rejection_ledger
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            latest_runtime_cycle = conn.execute(
                """
                SELECT id, status, started_at, completed_at
                FROM cycles
                WHERE trigger_source = 'runtime.market_service'
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            runtime_ranked = (
                conn.execute(
                    """
                    SELECT
                        rs.market_id,
                        COALESCE(rs.adaptive_rank, rs.base_score) AS total_rank_score,
                        rs.rank_position,
                        CASE
                            WHEN rs.selected_flag THEN 'TOP'
                            WHEN rs.rank_position <= 5 THEN 'WATCH'
                            ELSE 'MONITOR'
                        END AS rank_tier_class,
                        CASE
                            WHEN rs.eligible_flag THEN 'SELECTABLE'
                            ELSE 'BLOCKED'
                        END AS gate_decision_class,
                        CASE
                            WHEN rs.selected_flag THEN 'PRIMARY'
                            ELSE 'RUNTIME'
                        END AS gate_priority_class,
                        COALESCE(rs.recommendation_reason, rs.reject_reason, 'runtime_refresh_snapshot')
                            AS selection_reason_text,
                        ms.captured_at AS created_at
                    FROM ranking_snapshots rs
                    JOIN market_snapshots ms ON ms.id = rs.market_snapshot_id
                    WHERE rs.cycle_id = %s
                    ORDER BY rs.rank_position ASC NULLS LAST, rs.market_id ASC
                    LIMIT %s
                    """,
                    (str(latest_runtime_cycle["id"]), limit),
                ).fetchall()
                if latest_runtime_cycle is not None
                else []
            )
            runtime_selected_count = (
                conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM ranking_snapshots
                    WHERE cycle_id = %s
                      AND eligible_flag = TRUE
                    """,
                    (str(latest_runtime_cycle["id"]),),
                ).fetchone()["count"]
                if latest_runtime_cycle is not None
                else 0
            )
            use_runtime_fallback = latest_runtime_cycle is not None and (
                latest_policy_run is None
                or (
                    latest_policy_run["started_at"] is not None
                    and latest_runtime_cycle["started_at"] is not None
                    and latest_runtime_cycle["started_at"] > latest_policy_run["started_at"]
                )
            )

        if use_runtime_fallback:
            runtime_run = {
                "id": str(latest_runtime_cycle["id"]),
                "status": latest_runtime_cycle["status"],
                "started_at": latest_runtime_cycle["started_at"],
                "ended_at": latest_runtime_cycle["completed_at"],
            }
            serialized_runtime = [_row_dict(row) for row in runtime_ranked]
            return {
                "latest_ranking_policy_run": _row_dict(runtime_run),
                "top_ranked": serialized_runtime,
                "recent_candidates": serialized_runtime,
                "selected_candidate_count": runtime_selected_count,
                "rejected_candidates": [],
                "rejection_ledger": [_row_dict(row) for row in rejection_ledger],
            }

        return {
            "latest_ranking_policy_run": _row_dict(latest_policy_run),
            "top_ranked": [_row_dict(row) for row in top_ranked],
            "recent_candidates": [_row_dict(row) for row in recent_candidates],
            "selected_candidate_count": selected_count,
            "rejected_candidates": [_row_dict(row) for row in rejected],
            "rejection_ledger": [_row_dict(row) for row in rejection_ledger],
        }

    def get_positions_orders(self, limit: int = 10) -> dict[str, object]:
        with self._factory.connect() as conn:
            live_positions = conn.execute(
                """
                SELECT market_id, side, size, avg_entry, current_status, unrealized, realized, updated_at
                FROM positions
                WHERE closed_at IS NULL
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            paper_positions = conn.execute(
                """
                SELECT market_id, intended_outcome, size, avg_entry, current_status, unrealized, realized, updated_at, closed_at
                FROM paper_positions
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            shadow_positions = conn.execute(
                """
                SELECT market_id, intended_outcome, size, avg_entry, current_status, unrealized, realized, updated_at
                FROM shadow_positions
                WHERE closed_at IS NULL
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            live_orders = conn.execute(
                """
                SELECT market_id, action, side, price, size, notional, status, updated_at
                FROM live_orders
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            paper_orders = conn.execute(
                """
                SELECT market_id, action, intended_outcome, intended_price, intended_size, notional, status, updated_at
                FROM paper_orders
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            shadow_orders = conn.execute(
                """
                SELECT market_id, action, intended_outcome, intended_price, intended_size, notional, status, updated_at
                FROM shadow_orders
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()

        return {
            "live_positions": [_row_dict(row) for row in live_positions],
            "paper_positions": [_row_dict(row) for row in paper_positions],
            "shadow_positions": [_row_dict(row) for row in shadow_positions],
            "live_orders": [_row_dict(row) for row in live_orders],
            "paper_orders": [_row_dict(row) for row in paper_orders],
            "shadow_orders": [_row_dict(row) for row in shadow_orders],
            "pnl": self.get_pnl_snapshot(),
        }

    def get_pnl_snapshot(self) -> dict[str, object]:
        with self._factory.connect() as conn:
            live = conn.execute(
                "SELECT COALESCE(SUM(unrealized), 0) AS unrealized, COALESCE(SUM(realized), 0) AS realized FROM positions WHERE closed_at IS NULL"
            ).fetchone()
            paper = conn.execute(
                """
                SELECT
                    COALESCE(SUM(unrealized) FILTER (WHERE closed_at IS NULL), 0) AS unrealized,
                    COALESCE(SUM(realized), 0) AS realized
                FROM paper_positions
                """
            ).fetchone()
            shadow = conn.execute(
                "SELECT COALESCE(SUM(unrealized), 0) AS unrealized, COALESCE(SUM(realized), 0) AS realized FROM shadow_positions WHERE closed_at IS NULL"
            ).fetchone()
        return {
            "live": _row_dict(live),
            "paper": _row_dict(paper),
            "shadow": _row_dict(shadow),
        }

    def get_invalidation_exit_layers(self, limit: int = 10) -> dict[str, object]:
        with self._factory.connect() as conn:
            invalidations = conn.execute(
                """
                SELECT market_id, invalidation_state_class, exit_policy_class, deployment_gate_effect, policy_reason_text, created_at
                FROM invalidation_policy_records
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            advisories = conn.execute(
                """
                SELECT market_id, exposure_type, advisory_action_class, advisory_priority_class, advisory_reason_text, created_at
                FROM exit_advisory_records
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            resolutions = conn.execute(
                """
                SELECT market_id, primary_advisory_action_class, primary_priority_class, action_readiness_class, conflict_status_class, created_at
                FROM advisory_resolution_records
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            intents = conn.execute(
                """
                SELECT market_id, exposure_type, command_intent_class, command_priority_class, command_status_class,
                       orchestration_eligibility_class, created_at
                FROM command_intent_records
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()

        return {
            "invalidation_policy_records": [_row_dict(row) for row in invalidations],
            "exit_advisory_records": [_row_dict(row) for row in advisories],
            "advisory_resolution_records": [_row_dict(row) for row in resolutions],
            "command_intent_records": [_row_dict(row) for row in intents],
        }

    def get_intelligence_panels(self, limit: int = 10) -> dict[str, object]:
        settings = get_settings()
        with self._factory.connect() as conn:
            whales = conn.execute(
                """
                SELECT market_id, whale_presence_score, whale_conviction_score, smart_whale_alignment_score,
                       whale_reversal_risk, scoring_reason_text, created_at
                FROM whale_market_scores
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            news = conn.execute(
                """
                SELECT normalized_title, normalized_summary, source_category, canonical_url, published_at, created_at
                FROM external_events_normalized
                WHERE status = 'READY'
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            cognition = conn.execute(
                """
                SELECT market_id, cognition_conclusion_class, overall_confidence_score, caution_score,
                       usability_class, concise_narration_text AS summary_text, created_at
                FROM cognition_summaries
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            sources = conn.execute(
                """
                SELECT source_key, source_name, source_type, base_url, is_enabled, metadata_json, updated_at
                FROM intelligence_sources
                ORDER BY source_name ASC
                """
            ).fetchall()
            source_runs = conn.execute(
                """
                SELECT DISTINCT ON (sources.source_key)
                       sources.source_key, runs.status, runs.started_at, runs.ended_at, runs.fetched_count, runs.normalized_count
                FROM intelligence_sources sources
                LEFT JOIN intelligence_ingestion_runs runs ON runs.intelligence_source_id = sources.id
                ORDER BY sources.source_key, runs.started_at DESC NULLS LAST, runs.id DESC NULLS LAST
                """
            ).fetchall()
            latest_whale_scan = conn.execute(
                """
                SELECT started_at, ended_at, status, success_count, failure_count
                FROM whale_scan_runs
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            latest_whale_scoring = conn.execute(
                """
                SELECT started_at, ended_at, status, success_count, failure_count
                FROM whale_scoring_runs
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            latest_ai_digest = conn.execute(
                """
                SELECT title, body_text, payload_json, source_ref, created_at
                FROM alert_events
                WHERE event_class = 'AI_INTELLIGENCE_DIGEST'
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            latest_handoff = conn.execute(
                """
                SELECT started_at, ended_at, status, sent_count, held_count, skipped_count
                FROM cognition_handoff_runs
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            latest_ranking_with_whales = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM ranking_v2_candidates
                WHERE whale_market_score_id IS NOT NULL
                """
            ).fetchone()["count"]
            latest_trade_with_cognition = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM trade_classifications
                WHERE cognition_summary_id IS NOT NULL
                """
            ).fetchone()["count"]

        runs_by_source_key = {str(row["source_key"]): _row_dict(row) for row in source_runs}
        source_details: list[dict[str, object]] = []
        active_sources: list[str] = []
        for row in sources:
            payload = _row_dict(row) or {}
            source_key = str(row["source_key"])
            latest_run = runs_by_source_key.get(source_key)
            if bool(row["is_enabled"]):
                active_sources.append(source_key)
            payload["latest_run"] = latest_run
            payload["freshness_status"] = _freshness_status(
                latest_run["ended_at"] if latest_run is not None else None,
                stale_after_seconds=settings.intelligence_news_stale_after_seconds,
            )
            source_details.append(payload)

        return {
            "whales": [_row_dict(row) for row in whales],
            "news": [_row_dict(row) for row in news],
            "cognition": [_row_dict(row) for row in cognition],
            "news_state": {
                "active_sources": active_sources,
                "sources": source_details,
                "freshness_status": _freshness_status(
                    max(
                        (
                            row["ended_at"]
                            for row in source_runs
                            if row["ended_at"] is not None
                        ),
                        default=None,
                    ),
                    stale_after_seconds=settings.intelligence_news_stale_after_seconds,
                ),
                "handoff_state": _row_dict(latest_handoff),
                "handoff_freshness": _freshness_status(
                    latest_handoff["ended_at"] if latest_handoff is not None else None,
                    stale_after_seconds=settings.intelligence_news_stale_after_seconds,
                ),
                "affecting_current_context": latest_trade_with_cognition > 0,
            },
            "whale_state": {
                "latest_scan_run": _row_dict(latest_whale_scan),
                "latest_scoring_run": _row_dict(latest_whale_scoring),
                "freshness_status": _freshness_status(
                    latest_whale_scoring["ended_at"] if latest_whale_scoring is not None else None,
                    stale_after_seconds=settings.intelligence_whale_stale_after_seconds,
                ),
                "integration_mode": "runtime_scoring_with_manual_or_external_event_supply",
                "affecting_current_context": latest_ranking_with_whales > 0,
            },
            "ai_state": {
                "enabled": bool(settings.intelligence_ai_enabled and os.getenv("ANTHROPIC_API_KEY")),
                "latest_digests": [_row_dict(row) for row in latest_ai_digest],
                "freshness_status": _freshness_status(
                    latest_ai_digest[0]["created_at"] if latest_ai_digest else None,
                    stale_after_seconds=settings.intelligence_ai_stale_after_seconds,
                ),
                "latest_cognition_summary_at": _iso_or_none(cognition[0]["created_at"]) if cognition else None,
                "affecting_current_context": latest_trade_with_cognition > 0,
            },
        }

    def get_audit_views(self, limit: int = 10) -> dict[str, object]:
        with self._factory.connect() as conn:
            decisions = conn.execute(
                """
                SELECT cycle_id, market_id, decision_type, selected, reason, confidence, trade_type, bucket_type, created_at
                FROM decision_ledger
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            rejections = conn.execute(
                """
                SELECT cycle_id, market_id, stage, reason_code, reason_text, created_at
                FROM rejection_ledger
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            control_actions = conn.execute(
                """
                SELECT action_class, requested_via, requested_by, status_class, reason_text, created_at
                FROM operator_control_actions
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            alerts = conn.execute(
                """
                SELECT event_class, severity_class, title, body_text, delivery_status_class, created_at
                FROM alert_events
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            paper_order_events = conn.execute(
                """
                SELECT paper_order_id, new_status, reason_code, reason_text, event_at, created_at
                FROM paper_order_events
                ORDER BY event_at DESC, created_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            paper_position_events = conn.execute(
                """
                SELECT paper_position_id, event_type, reason_code, reason_text, event_at, created_at
                FROM paper_position_events
                ORDER BY event_at DESC, created_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            shadow_order_events = conn.execute(
                """
                SELECT shadow_order_id, new_status, reason_code, reason_text, event_at, created_at
                FROM shadow_order_events
                ORDER BY event_at DESC, created_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            shadow_position_events = conn.execute(
                """
                SELECT shadow_position_id, event_type, reason_code, reason_text, event_at, created_at
                FROM shadow_position_events
                ORDER BY event_at DESC, created_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            live_order_status_history = conn.execute(
                """
                SELECT order_id, old_status, new_status, source, reason, exchange_status, event_at, created_at
                FROM order_status_history
                ORDER BY event_at DESC, created_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            live_position_events = conn.execute(
                """
                SELECT position_id, event_type, reason, event_at, created_at
                FROM position_events
                ORDER BY event_at DESC, created_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()

        return {
            "decision_ledger": [_row_dict(row) for row in decisions],
            "rejection_ledger": [_row_dict(row) for row in rejections],
            "operator_control_actions": [_row_dict(row) for row in control_actions],
            "alert_events": [_row_dict(row) for row in alerts],
            "live_order_status_history": [_row_dict(row) for row in live_order_status_history],
            "live_position_events": [_row_dict(row) for row in live_position_events],
            "paper_order_events": [_row_dict(row) for row in paper_order_events],
            "paper_position_events": [_row_dict(row) for row in paper_position_events],
            "shadow_order_events": [_row_dict(row) for row in shadow_order_events],
            "shadow_position_events": [_row_dict(row) for row in shadow_position_events],
        }

    def get_dashboard_overview(self, limit: int = 8) -> dict[str, object]:
        runtime_health = HealthTruthService(connection_factory=self._factory).get_health_truth()
        event_bus = self._event_bus_overview()
        data_foundation = self._data_foundation_overview()
        ai_brain = self._ai_brain_overview()
        news_neuron = self._news_neuron_overview()
        rules_neuron = self._rules_neuron_overview()
        social_neuron = self._social_neuron_overview()
        whale_neuron = self._whale_neuron_overview()
        market_technical = self._market_technical_overview()
        market_memory = self._market_memory_overview()
        brains = self._brains_overview()
        opportunities = self._opportunities_overview()
        strategy = self._strategy_overview()
        capital = self._capital_overview()
        risk = self._risk_overview()
        execution = self._execution_overview()
        exits = self._exit_overview()
        no_trade = self._no_trade_overview()
        learning = self._learning_overview()
        return {
            "system_health": self.get_system_health(),
            "runtime": {
                "current_mode": runtime_health.get("current_mode"),
                "kill_switch_active": runtime_health.get("kill_switch_active"),
                "cooldown_active": runtime_health.get("cooldown_active"),
                "attack_mode_active": runtime_health.get("attack_mode_active"),
                "last_mode_change": (runtime_health.get("last_mode_transition") or {}).get("created_at") if isinstance(runtime_health.get("last_mode_transition"), dict) else None,
                "last_reason": (runtime_health.get("last_mode_transition") or {}).get("reason") if isinstance(runtime_health.get("last_mode_transition"), dict) else None,
                "last_actor": (runtime_health.get("last_mode_transition") or {}).get("actor") if isinstance(runtime_health.get("last_mode_transition"), dict) else None,
                "overall_runtime_health": runtime_health.get("overall_status"),
                "active_cycle": runtime_health.get("active_cycle"),
                "service_count": len(runtime_health.get("services") or []),
                "degraded_services": len(runtime_health.get("stale_services") or []),
            },
            "event_bus": event_bus,
            "data_foundation": data_foundation,
            "ai_brain": ai_brain,
            "news_neuron": news_neuron,
            "rules_neuron": rules_neuron,
            "social_neuron": social_neuron,
            "whale_neuron": whale_neuron,
            "market_technical": market_technical,
            "market_memory": market_memory,
            "brains": brains,
            "opportunities": opportunities,
            "strategy": strategy,
            "capital": capital,
            "risk": risk,
            "execution": execution,
            "exits": exits,
            "no_trade": no_trade,
            "learning": learning,
            "kpi_quality": self.get_kpi_quality(recent_cycles=min(limit, 10), top_reasons_limit=min(limit, 8)),
            "ranking": self.get_ranking_overview(limit=limit),
            "positions_orders": self.get_positions_orders(limit=limit),
            "invalidation_exit": self.get_invalidation_exit_layers(limit=limit),
            "intelligence": self.get_intelligence_panels(limit=limit),
            "audit": self.get_audit_views(limit=limit),
        }

    def _execution_overview(self) -> dict[str, object]:
        empty = {
            "execution_status": "DISABLED" if not self._factory.enabled else "EMPTY",
            "live_certified": False,
            "orders_today": 0,
            "paper_orders_today": 0,
            "shadow_plans_today": 0,
            "fills_today": 0,
            "partial_fills_today": 0,
            "failed_fills_today": 0,
            "cancelled_today": 0,
            "avg_slippage_bps": None,
            "avg_quality_score": None,
            "recent_orders": [],
            "recent_fills": [],
            "recent_errors": [],
            "recent_quality": [],
            "live_blocked_count": 0,
            "errors": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass(%s) AS name", ("orders_v2",)).fetchone()["name"]
                if not exists:
                    return empty
                order_stats = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS orders_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND execution_mode='PAPER_SIM') AS paper_orders_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND execution_mode='SHADOW_PLAN') AS shadow_plans_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND order_status='CANCELLED') AS cancelled_today
                    FROM orders_v2
                    """
                ).fetchone()
                fill_stats = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS fills_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND partial IS TRUE) AS partial_fills_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND fill_status='FAILED') AS failed_fills_today,
                      AVG(slippage_bps) AS avg_slippage_bps
                    FROM fills_v2
                    """
                ).fetchone()
                quality = conn.execute("SELECT AVG(execution_quality_score) AS avg_quality_score FROM execution_quality WHERE created_at::date=CURRENT_DATE").fetchone()
                recent_orders = conn.execute("SELECT order_id, market_id, side, engine, execution_mode, order_status, size_usd, filled_size, remaining_size, created_at FROM orders_v2 ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
                recent_fills = conn.execute("SELECT fill_id, order_id, market_id, fill_status, filled_size, fill_price, slippage_bps, partial, created_at FROM fills_v2 ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
                recent_errors = conn.execute("SELECT error_id, market_id, order_id, error_type, severity, message, created_at FROM execution_errors ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
                recent_quality = conn.execute("SELECT quality_id, order_id, market_id, execution_quality_score, quality_flags_json, created_at FROM execution_quality ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
                live_blocked = conn.execute("SELECT COUNT(*) AS count FROM execution_errors WHERE error_type='LIVE_NOT_CERTIFIED' OR message ILIKE '%live_not_certified%'").fetchone()
            return {
                "execution_status": "OK" if int((order_stats or {}).get("orders_today") or 0) or int((fill_stats or {}).get("fills_today") or 0) else "EMPTY",
                "live_certified": False,
                "orders_today": int((order_stats or {}).get("orders_today") or 0),
                "paper_orders_today": int((order_stats or {}).get("paper_orders_today") or 0),
                "shadow_plans_today": int((order_stats or {}).get("shadow_plans_today") or 0),
                "fills_today": int((fill_stats or {}).get("fills_today") or 0),
                "partial_fills_today": int((fill_stats or {}).get("partial_fills_today") or 0),
                "failed_fills_today": int((fill_stats or {}).get("failed_fills_today") or 0),
                "cancelled_today": int((order_stats or {}).get("cancelled_today") or 0),
                "avg_slippage_bps": _float_or_none((fill_stats or {}).get("avg_slippage_bps")),
                "avg_quality_score": _float_or_none((quality or {}).get("avg_quality_score")),
                "recent_orders": [_row_dict(row) for row in recent_orders],
                "recent_fills": [_row_dict(row) for row in recent_fills],
                "recent_errors": [_row_dict(row) for row in recent_errors],
                "recent_quality": [_row_dict(row) for row in recent_quality],
                "live_blocked_count": int((live_blocked or {}).get("count") or 0),
                "errors": [],
            }
        except Exception as exc:
            empty["execution_status"] = "ERROR"
            empty["errors"] = [str(exc)]
            return empty

    def _exit_overview(self) -> dict[str, object]:
        empty = {
            "exit_status": "DISABLED" if not self._factory.enabled else "EMPTY",
            "active_exit_plans": 0,
            "exit_intents_today": 0,
            "triggers_today": 0,
            "failures_today": 0,
            "orphan_orders_count": 0,
            "avg_exit_quality": None,
            "recent_exit_plans": [],
            "recent_exit_intents": [],
            "recent_exit_failures": [],
            "common_exit_reasons": [],
            "live_certified": False,
            "errors": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass(%s) AS name", ("exit_plans",)).fetchone()["name"]
                if not exists:
                    return empty
                plan_stats = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE plan_status IN ('ACTIVE','PENDING_ORDER')) AS active_exit_plans,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND insufficient_data IS TRUE) AS insufficient_data_today
                    FROM exit_plans
                    """
                ).fetchone()
                intents = conn.execute("SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS exit_intents_today FROM exit_intents").fetchone()
                events = conn.execute("SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND event_type LIKE '%TRIGGERED%') AS triggers_today FROM exit_events").fetchone()
                failures = conn.execute("SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS failures_today FROM exit_failures").fetchone()
                quality = conn.execute("SELECT AVG(exit_quality_score) AS avg_exit_quality FROM exit_quality WHERE created_at::date=CURRENT_DATE").fetchone()
                recent_plans = conn.execute("SELECT exit_plan_id, market_id, side, engine, order_id, plan_status, insufficient_data, created_at FROM exit_plans ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
                recent_intents = conn.execute("SELECT exit_intent_id, exit_plan_id, market_id, reason, intent_status, execution_mode, paper_shadow_only, created_at FROM exit_intents ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
                recent_failures = conn.execute("SELECT failure_id, exit_plan_id, market_id, failure_type, severity, reason, created_at FROM exit_failures ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
                common_reasons = conn.execute("SELECT reason, COUNT(*) AS count FROM exit_intents GROUP BY reason ORDER BY count DESC, reason LIMIT 5").fetchall()
                if conn.execute("SELECT to_regclass(%s) AS name", ("orders_v2",)).fetchone()["name"]:
                    orphans = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM orders_v2 o
                        LEFT JOIN exit_plans p ON p.order_id=o.order_id OR p.exit_plan_id=o.exit_plan_id
                        WHERE o.order_status IN ('SUBMITTED_PAPER','PLANNED_SHADOW','PARTIALLY_FILLED','FILLED')
                          AND p.id IS NULL
                        """
                    ).fetchone()
                else:
                    orphans = {"count": 0}
            return {
                "exit_status": "OK" if int((plan_stats or {}).get("active_exit_plans") or 0) or int((intents or {}).get("exit_intents_today") or 0) else "EMPTY",
                "active_exit_plans": int((plan_stats or {}).get("active_exit_plans") or 0),
                "exit_intents_today": int((intents or {}).get("exit_intents_today") or 0),
                "triggers_today": int((events or {}).get("triggers_today") or 0),
                "failures_today": int((failures or {}).get("failures_today") or 0),
                "orphan_orders_count": int((orphans or {}).get("count") or 0),
                "avg_exit_quality": _float_or_none((quality or {}).get("avg_exit_quality")),
                "recent_exit_plans": [_row_dict(row) for row in recent_plans],
                "recent_exit_intents": [_row_dict(row) for row in recent_intents],
                "recent_exit_failures": [_row_dict(row) for row in recent_failures],
                "common_exit_reasons": [_row_dict(row) for row in common_reasons],
                "live_certified": False,
                "errors": [],
            }
        except Exception as exc:
            empty["exit_status"] = "ERROR"
            empty["errors"] = [str(exc)]
            return empty

    def _no_trade_overview(self) -> dict[str, object]:
        empty = {
            "no_trade_status": "DISABLED" if not self._factory.enabled else "EMPTY",
            "logged_today": 0,
            "top_no_trade_reasons": [],
            "no_trade_by_engine": [],
            "no_trade_by_market_family": [],
            "pending_reviews": 0,
            "high_regret_count": 0,
            "good_no_trade_count": 0,
            "insufficient_data_count": 0,
            "regret_analysis": {},
            "recent_no_trade_logs": [],
            "recent_high_regret": [],
            "errors": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass(%s) AS name", ("no_trade_log",)).fetchone()["name"]
                if not exists:
                    return empty
                stats = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS logged_today,
                      COUNT(*) FILTER (WHERE insufficient_data IS TRUE) AS insufficient_data_count
                    FROM no_trade_log
                    """
                ).fetchone()
                top_reasons = conn.execute("SELECT reason, severity, COUNT(*) AS count FROM no_trade_reasons GROUP BY reason, severity ORDER BY count DESC, reason LIMIT 5").fetchall()
                by_engine = conn.execute("SELECT COALESCE(candidate_engine,'UNKNOWN') AS candidate_engine, COUNT(*) AS count FROM no_trade_log GROUP BY COALESCE(candidate_engine,'UNKNOWN') ORDER BY count DESC LIMIT 5").fetchall()
                by_family = conn.execute("SELECT COALESCE(market_family,'UNKNOWN') AS market_family, COUNT(*) AS count FROM no_trade_log GROUP BY COALESCE(market_family,'UNKNOWN') ORDER BY count DESC LIMIT 5").fetchall()
                pending = conn.execute("SELECT COUNT(*) AS count FROM no_trade_post_fact_review WHERE review_status='PENDING'").fetchone()
                regret = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE regret_band='HIGH_REGRET') AS high_regret_count,
                      COUNT(*) FILTER (WHERE regret_band='GOOD_NO_TRADE') AS good_no_trade_count,
                      COUNT(*) FILTER (WHERE regret_band='INSUFFICIENT_DATA') AS insufficient_regret_count,
                      AVG(regret_score) AS avg_regret_score
                    FROM no_trade_regret_score
                    """
                ).fetchone()
                recent = conn.execute("SELECT no_trade_id, market_id, candidate_engine, source_layer, decision_status, primary_reason, created_at FROM no_trade_log ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
                recent_high = conn.execute("SELECT regret_id, no_trade_id, market_id, regret_score, regret_band, learning_signal, created_at FROM no_trade_regret_score WHERE regret_band='HIGH_REGRET' ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
            return {
                "no_trade_status": "OK" if int((stats or {}).get("logged_today") or 0) else "EMPTY",
                "logged_today": int((stats or {}).get("logged_today") or 0),
                "top_no_trade_reasons": [_row_dict(row) for row in top_reasons],
                "no_trade_by_engine": [_row_dict(row) for row in by_engine],
                "no_trade_by_market_family": [_row_dict(row) for row in by_family],
                "pending_reviews": int((pending or {}).get("count") or 0),
                "high_regret_count": int((regret or {}).get("high_regret_count") or 0),
                "good_no_trade_count": int((regret or {}).get("good_no_trade_count") or 0),
                "insufficient_data_count": int((stats or {}).get("insufficient_data_count") or 0),
                "regret_analysis": _row_dict(regret or {}),
                "recent_no_trade_logs": [_row_dict(row) for row in recent],
                "recent_high_regret": [_row_dict(row) for row in recent_high],
                "errors": [],
            }
        except Exception as exc:
            empty["no_trade_status"] = "ERROR"
            empty["errors"] = [str(exc)]
            return empty

    def _learning_overview(self) -> dict[str, object]:
        empty = {
            "learning_status": "DISABLED" if not self._factory.enabled else "EMPTY",
            "trade_reviews_today": 0,
            "pending_reviews": 0,
            "engine_learning_summary": [],
            "source_learning_summary": [],
            "whale_learning_summary": [],
            "ai_learning_summary": [],
            "no_trade_learning_summary": [],
            "model_adjustments_pending": 0,
            "insufficient_data_count": 0,
            "latest_review": None,
            "recent_learning_events": [],
            "errors": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass(%s) AS name", ("trade_reviews",)).fetchone()["name"]
                if not exists:
                    return empty
                stats = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS trade_reviews_today,
                      COUNT(*) FILTER (WHERE review_status='PENDING') AS pending_reviews,
                      COUNT(*) FILTER (WHERE insufficient_data IS TRUE) AS insufficient_trade_reviews
                    FROM trade_reviews
                    """
                ).fetchone()
                latest = conn.execute("SELECT review_id, market_id, engine, engine_result, review_status, created_at FROM trade_reviews ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
                engine_summary = conn.execute("SELECT engine, learning_signal, COUNT(*) AS count, AVG(confidence) AS avg_confidence FROM engine_learning GROUP BY engine, learning_signal ORDER BY count DESC LIMIT 8").fetchall()
                source_summary = conn.execute("SELECT source_type, learning_signal, COUNT(*) AS count, AVG(confidence) AS avg_confidence FROM source_learning GROUP BY source_type, learning_signal ORDER BY count DESC LIMIT 8").fetchall()
                whale_summary = conn.execute("SELECT whale_id, learning_signal, COUNT(*) AS count, AVG(confidence) AS avg_confidence FROM whale_learning GROUP BY whale_id, learning_signal ORDER BY count DESC LIMIT 8").fetchall()
                ai_summary = conn.execute("SELECT COALESCE(model_name,'UNKNOWN') AS model_name, task_type, learning_signal, COUNT(*) AS count, AVG(accuracy_score) AS avg_accuracy FROM ai_learning GROUP BY COALESCE(model_name,'UNKNOWN'), task_type, learning_signal ORDER BY count DESC LIMIT 8").fetchall()
                no_trade_summary = conn.execute("SELECT regret_band, learning_signal, COUNT(*) AS count, AVG(confidence) AS avg_confidence FROM no_trade_learning GROUP BY regret_band, learning_signal ORDER BY count DESC LIMIT 8").fetchall()
                adjustments = conn.execute("SELECT COUNT(*) AS count FROM model_adjustments WHERE status IN ('RECOMMENDED','REVIEW_REQUIRED')").fetchone()
                nt_insufficient = conn.execute("SELECT COUNT(*) AS count FROM no_trade_learning WHERE learning_signal='improve_data'").fetchone()
                recent_events = conn.execute(
                    "SELECT event_id, event_type, aggregate_id, stored_at AS created_at FROM event_log WHERE event_type LIKE 'learning.%' ORDER BY stored_at DESC, id DESC LIMIT 8"
                ).fetchall() if conn.execute("SELECT to_regclass(%s) AS name", ("event_log",)).fetchone()["name"] else []
            reviews_today = int((stats or {}).get("trade_reviews_today") or 0)
            return {
                "learning_status": "OK" if reviews_today or engine_summary or no_trade_summary else "EMPTY",
                "trade_reviews_today": reviews_today,
                "pending_reviews": int((stats or {}).get("pending_reviews") or 0),
                "engine_learning_summary": [_row_dict(row) for row in engine_summary],
                "source_learning_summary": [_row_dict(row) for row in source_summary],
                "whale_learning_summary": [_row_dict(row) for row in whale_summary],
                "ai_learning_summary": [_row_dict(row) for row in ai_summary],
                "no_trade_learning_summary": [_row_dict(row) for row in no_trade_summary],
                "model_adjustments_pending": int((adjustments or {}).get("count") or 0),
                "insufficient_data_count": int((stats or {}).get("insufficient_trade_reviews") or 0) + int((nt_insufficient or {}).get("count") or 0),
                "latest_review": _row_dict(latest),
                "recent_learning_events": [_row_dict(row) for row in recent_events],
                "errors": [],
            }
        except Exception as exc:
            empty["learning_status"] = "ERROR"
            empty["errors"] = [str(exc)]
            return empty

    def _risk_overview(self) -> dict[str, object]:
        empty = {
            "risk_status": "DISABLED" if not self._factory.enabled else "EMPTY",
            "governor_status": None,
            "kill_switch_active": False,
            "attack_mode_allowed": False,
            "cooldown_active": False,
            "gate_runs_today": 0,
            "approved_today": 0,
            "blocked_today": 0,
            "breaches_today": 0,
            "active_cooldowns": 0,
            "max_daily_loss": None,
            "daily_loss": None,
            "max_weekly_loss": None,
            "weekly_loss": None,
            "open_positions_count": 0,
            "open_exposure": None,
            "recent_gate_decisions": [],
            "recent_breaches": [],
            "recent_cooldowns": [],
            "latest_manual_override": None,
            "insufficient_data_count": 0,
            "errors": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass('risk_governor_state') AS name").fetchone()
                if exists is None or exists["name"] is None:
                    return empty
                state = conn.execute("SELECT * FROM risk_governor_state ORDER BY updated_at DESC, id DESC LIMIT 1").fetchone()
                stats = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM risk_gate_runs WHERE created_at::date=CURRENT_DATE) AS gate_runs_today,
                        COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND decision='APPROVED') AS approved_today,
                        COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND blocked IS TRUE) AS blocked_today,
                        COUNT(*) FILTER (WHERE decision='INSUFFICIENT_DATA') AS insufficient_data_count
                    FROM risk_gate_decisions
                    """
                ).fetchone()
                breaches_count = conn.execute("SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS count FROM risk_breaches").fetchone()
                cooldowns_count = conn.execute("SELECT COUNT(*) AS count FROM cooldown_events WHERE active IS TRUE AND (expires_at IS NULL OR expires_at > now())").fetchone()
                recent_gate = conn.execute("SELECT market_id, engine, decision, risk_score, block_reasons_json, created_at FROM risk_gate_decisions ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
                recent_breaches = conn.execute("SELECT breach_type, severity, market_id, engine, blocked, explanation, created_at FROM risk_breaches ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
                recent_cooldowns = conn.execute("SELECT scope, scope_key, engine, market_family, reason, active, expires_at, created_at FROM cooldown_events ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
                override = conn.execute("SELECT * FROM risk_governor_events WHERE event_type='risk.manual_override.created' ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return {
                "risk_status": "OK" if state else "EMPTY",
                "governor_status": (state or {}).get("governor_status"),
                "kill_switch_active": bool((state or {}).get("kill_switch_active")),
                "attack_mode_allowed": bool((state or {}).get("attack_mode_allowed")),
                "cooldown_active": bool((state or {}).get("cooldown_active")),
                "gate_runs_today": int((stats or {}).get("gate_runs_today") or 0),
                "approved_today": int((stats or {}).get("approved_today") or 0),
                "blocked_today": int((stats or {}).get("blocked_today") or 0),
                "breaches_today": int((breaches_count or {}).get("count") or 0),
                "active_cooldowns": int((cooldowns_count or {}).get("count") or 0),
                "max_daily_loss": _float_or_none((state or {}).get("max_daily_loss_usd")),
                "daily_loss": _float_or_none((state or {}).get("daily_loss_usd")),
                "max_weekly_loss": _float_or_none((state or {}).get("max_weekly_loss_usd")),
                "weekly_loss": _float_or_none((state or {}).get("weekly_loss_usd")),
                "open_positions_count": int((state or {}).get("open_positions_count") or 0),
                "open_exposure": _float_or_none((state or {}).get("open_exposure_usd")),
                "recent_gate_decisions": [_row_dict(row) for row in recent_gate],
                "recent_breaches": [_row_dict(row) for row in recent_breaches],
                "recent_cooldowns": [_row_dict(row) for row in recent_cooldowns],
                "latest_manual_override": _row_dict(override) if override else None,
                "insufficient_data_count": int((stats or {}).get("insufficient_data_count") or 0),
                "errors": [],
            }
        except Exception as exc:
            empty["risk_status"] = "ERROR"
            empty["errors"] = [str(exc)]
            return empty

    def _capital_overview(self) -> dict[str, object]:
        empty = {
            "capital_status": "DISABLED" if not self._factory.enabled else "EMPTY",
            "total_capital": None,
            "available_capital": None,
            "locked_capital": None,
            "survival_reserve": None,
            "cash_reserve": None,
            "profit_pocket": None,
            "attack_bank": None,
            "allocations_today": 0,
            "blocked_allocations_today": 0,
            "reduced_allocations_today": 0,
            "budgets_by_engine": [],
            "allocation_by_bucket": [],
            "recent_capital_events": [],
            "loss_streak_count": 0,
            "reinvest_status": "EMPTY",
            "insufficient_data_count": 0,
            "errors": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass('capital_state_v2') AS name").fetchone()
                if exists is None or exists["name"] is None:
                    return empty
                state = conn.execute("SELECT * FROM capital_state_v2 ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
                stats = conn.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) AS allocations_today,
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND allocation_status = 'BLOCKED') AS blocked_today,
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND allocation_status = 'REDUCED') AS reduced_today,
                        COUNT(*) FILTER (WHERE allocation_status = 'INSUFFICIENT_DATA') AS insufficient_data_count
                    FROM capital_allocations_v2
                    """
                ).fetchone()
                budgets = conn.execute(
                    """
                    SELECT engine, bucket, available_usd, max_position_usd, enabled
                    FROM engine_budgets
                    ORDER BY engine, bucket
                    LIMIT 12
                    """
                ).fetchall()
                allocation_by_bucket = conn.execute(
                    """
                    SELECT bucket, allocation_status, COUNT(*) AS count, COALESCE(SUM(approved_size_usd), 0) AS approved_usd
                    FROM capital_allocations_v2
                    GROUP BY bucket, allocation_status
                    ORDER BY count DESC
                    LIMIT 10
                    """
                ).fetchall()
                events = conn.execute(
                    """
                    SELECT event_type, market_id, engine, bucket, amount_usd, reason, created_at
                    FROM capital_events
                    ORDER BY created_at DESC, id DESC
                    LIMIT 8
                    """
                ).fetchall()
                pocket = conn.execute("SELECT * FROM profit_pocket ORDER BY updated_at DESC, id DESC LIMIT 1").fetchone()
                attack = conn.execute("SELECT * FROM attack_bank ORDER BY updated_at DESC, id DESC LIMIT 1").fetchone()
            return {
                "capital_status": "OK" if state else "EMPTY",
                "total_capital": _float_or_none((state or {}).get("total_capital_usd")),
                "available_capital": _float_or_none((state or {}).get("available_capital_usd")),
                "locked_capital": _float_or_none((state or {}).get("locked_capital_usd")),
                "survival_reserve": _float_or_none((state or {}).get("survival_reserve_usd")),
                "cash_reserve": _float_or_none((state or {}).get("cash_reserve_usd")),
                "profit_pocket": _float_or_none((pocket or {}).get("available_profit_usd") or (state or {}).get("profit_pocket_usd")),
                "attack_bank": _float_or_none((attack or {}).get("available_usd") or (state or {}).get("attack_bank_usd")),
                "allocations_today": int((stats or {}).get("allocations_today") or 0),
                "blocked_allocations_today": int((stats or {}).get("blocked_today") or 0),
                "reduced_allocations_today": int((stats or {}).get("reduced_today") or 0),
                "budgets_by_engine": [_row_dict(row) for row in budgets],
                "allocation_by_bucket": [_row_dict(row) for row in allocation_by_bucket],
                "recent_capital_events": [_row_dict(row) for row in events],
                "loss_streak_count": int((state or {}).get("loss_streak_count") or 0),
                "reinvest_status": "OK" if pocket or attack else "EMPTY",
                "insufficient_data_count": int((stats or {}).get("insufficient_data_count") or 0),
                "errors": [],
            }
        except Exception as exc:
            empty["capital_status"] = "ERROR"
            empty["errors"] = [str(exc)]
            return empty

    def _strategy_overview(self) -> dict[str, object]:
        empty = {
            "strategy_status": "DISABLED" if not self._factory.enabled else "EMPTY",
            "runs_today": 0,
            "routes_today": 0,
            "no_trade_today": 0,
            "blocked_today": 0,
            "active_cooldowns": 0,
            "latest_route_ts": None,
            "routes_by_engine": [],
            "rejections_by_engine": [],
            "top_route_reasons": [],
            "common_rejection_reasons": [],
            "recent_routes": [],
            "recent_no_trade_routes": [],
            "engine_confidence_average": None,
            "errors": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass('strategy_routes_v2') AS name").fetchone()
                if exists is None or exists["name"] is None:
                    return empty
                stats = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM strategy_route_runs WHERE created_at::date = CURRENT_DATE) AS runs_today,
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) AS routes_today,
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND route_status = 'NO_TRADE') AS no_trade_today,
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND route_status = 'BLOCKED') AS blocked_today,
                        AVG(route_confidence) AS engine_confidence_average,
                        MAX(created_at) AS latest_route_ts
                    FROM strategy_routes_v2
                    """
                ).fetchone()
                cooldowns = conn.execute("SELECT COUNT(*) AS count FROM engine_cooldowns WHERE active IS TRUE AND (expires_at IS NULL OR expires_at > now())").fetchone()
                routes_by_engine = conn.execute(
                    """
                    SELECT selected_engine, route_status, COUNT(*) AS count
                    FROM strategy_routes_v2
                    GROUP BY selected_engine, route_status
                    ORDER BY count DESC, selected_engine ASC
                    LIMIT 8
                    """
                ).fetchall()
                rejections_by_engine = conn.execute(
                    """
                    SELECT engine, COUNT(*) AS count
                    FROM engine_rejections
                    GROUP BY engine
                    ORDER BY count DESC, engine ASC
                    LIMIT 8
                    """
                ).fetchall()
                route_reasons = conn.execute(
                    """
                    SELECT route_reason, COUNT(*) AS count
                    FROM strategy_routes_v2
                    GROUP BY route_reason
                    ORDER BY count DESC
                    LIMIT 8
                    """
                ).fetchall()
                rejection_reasons = conn.execute(
                    """
                    SELECT rejection_reason, COUNT(*) AS count
                    FROM engine_rejections
                    GROUP BY rejection_reason
                    ORDER BY count DESC, rejection_reason ASC
                    LIMIT 8
                    """
                ).fetchall()
                recent_routes = conn.execute(
                    """
                    SELECT market_id, side, selected_engine, route_status, route_confidence, route_reason, created_at
                    FROM strategy_routes_v2
                    ORDER BY created_at DESC, id DESC
                    LIMIT 5
                    """
                ).fetchall()
                no_trade = conn.execute(
                    """
                    SELECT market_id, side, selected_engine, route_status, no_trade_reasons_json, created_at
                    FROM strategy_routes_v2
                    WHERE selected_engine = 'NO_TRADE'
                    ORDER BY created_at DESC, id DESC
                    LIMIT 5
                    """
                ).fetchall()
            return {
                "strategy_status": "OK" if int((stats or {}).get("routes_today") or 0) else "EMPTY",
                "runs_today": int((stats or {}).get("runs_today") or 0),
                "routes_today": int((stats or {}).get("routes_today") or 0),
                "no_trade_today": int((stats or {}).get("no_trade_today") or 0),
                "blocked_today": int((stats or {}).get("blocked_today") or 0),
                "active_cooldowns": int((cooldowns or {}).get("count") or 0),
                "latest_route_ts": _iso_or_none((stats or {}).get("latest_route_ts")),
                "routes_by_engine": [_row_dict(row) for row in routes_by_engine],
                "rejections_by_engine": [_row_dict(row) for row in rejections_by_engine],
                "top_route_reasons": [_row_dict(row) for row in route_reasons],
                "common_rejection_reasons": [_row_dict(row) for row in rejection_reasons],
                "recent_routes": [_row_dict(row) for row in recent_routes],
                "recent_no_trade_routes": [_row_dict(row) for row in no_trade],
                "engine_confidence_average": _float_or_none((stats or {}).get("engine_confidence_average")),
                "errors": [],
            }
        except Exception as exc:
            empty["strategy_status"] = "ERROR"
            empty["errors"] = [str(exc)]
            return empty

    def _opportunities_overview(self) -> dict[str, object]:
        empty = {
            "opportunity_status": "DISABLED" if not self._factory.enabled else "EMPTY",
            "runs_today": 0,
            "scores_today": 0,
            "blocked_today": 0,
            "watchlist_today": 0,
            "high_score_today": 0,
            "latest_score_ts": None,
            "top_opportunities": [],
            "recent_blocked_opportunities": [],
            "common_risk_flags": [],
            "average_score": None,
            "average_confidence": None,
            "insufficient_data_count": 0,
            "top_candidate_engines": [],
            "errors": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass('opportunity_scores_v2') AS name").fetchone()
                if exists is None or exists["name"] is None:
                    return empty
                stats = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM opportunity_runs WHERE created_at::date = CURRENT_DATE) AS runs_today,
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) AS scores_today,
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND score_band = 'BLOCKED') AS blocked_today,
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND score_band = 'WATCHLIST') AS watchlist_today,
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND score_band = 'HIGH_CONVICTION') AS high_score_today,
                        COUNT(*) FILTER (WHERE insufficient_data IS TRUE) AS insufficient_data_count,
                        AVG(opportunity_score) AS average_score,
                        AVG(confidence) AS average_confidence,
                        MAX(created_at) AS latest_score_ts
                    FROM opportunity_scores_v2
                    """
                ).fetchone()
                top = conn.execute(
                    """
                    SELECT market_id, side, opportunity_score, score_band, confidence, candidate_engines_json, created_at
                    FROM opportunity_scores_v2
                    WHERE score_band <> 'BLOCKED' AND insufficient_data IS FALSE
                    ORDER BY opportunity_score DESC, confidence DESC, created_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                blocked = conn.execute(
                    """
                    SELECT market_id, side, score_band, no_trade_reasons_json, explanation, created_at
                    FROM opportunity_scores_v2
                    WHERE score_band = 'BLOCKED' OR capital_allowed IS FALSE OR technical_blocked IS TRUE
                    ORDER BY created_at DESC, id DESC
                    LIMIT 5
                    """
                ).fetchall()
                flags = conn.execute(
                    """
                    SELECT risk_flag, severity, COUNT(*) AS count
                    FROM opportunity_risk_flags
                    GROUP BY risk_flag, severity
                    ORDER BY count DESC, risk_flag ASC
                    LIMIT 8
                    """
                ).fetchall()
                engines = conn.execute(
                    """
                    SELECT value AS candidate_engine, COUNT(*) AS count
                    FROM opportunity_scores_v2, jsonb_array_elements_text(candidate_engines_json)
                    GROUP BY value
                    ORDER BY count DESC, value ASC
                    LIMIT 8
                    """
                ).fetchall()
            return {
                "opportunity_status": "OK" if int((stats or {}).get("scores_today") or 0) else "EMPTY",
                "runs_today": int((stats or {}).get("runs_today") or 0),
                "scores_today": int((stats or {}).get("scores_today") or 0),
                "blocked_today": int((stats or {}).get("blocked_today") or 0),
                "watchlist_today": int((stats or {}).get("watchlist_today") or 0),
                "high_score_today": int((stats or {}).get("high_score_today") or 0),
                "latest_score_ts": _iso_or_none((stats or {}).get("latest_score_ts")),
                "top_opportunities": [_row_dict(row) for row in top],
                "recent_blocked_opportunities": [_row_dict(row) for row in blocked],
                "common_risk_flags": [_row_dict(row) for row in flags],
                "average_score": _float_or_none((stats or {}).get("average_score")),
                "average_confidence": _float_or_none((stats or {}).get("average_confidence")),
                "insufficient_data_count": int((stats or {}).get("insufficient_data_count") or 0),
                "top_candidate_engines": [_row_dict(row) for row in engines],
                "errors": [],
            }
        except Exception as exc:
            empty["opportunity_status"] = "ERROR"
            empty["errors"] = [str(exc)]
            return empty

    def _brains_overview(self) -> dict[str, object]:
        empty = {
            "brain_status": "DISABLED" if not self._factory.enabled else "EMPTY",
            "context_runs_today": 0,
            "capital_runs_today": 0,
            "latest_context_shift": None,
            "latest_capital_allowed": None,
            "insufficient_data_count": 0,
            "capital_blocked_count": 0,
            "top_context_shifts": [],
            "top_capital_blocks": [],
            "average_context_confidence": None,
            "average_allocation_confidence": None,
            "common_context_risks": [],
            "common_capital_block_reasons": [],
            "latest_brain_update": None,
            "errors": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass('context_brain_outputs') AS name").fetchone()
                if exists is None or exists["name"] is None:
                    return empty
                stats = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM context_brain_runs WHERE created_at::date = CURRENT_DATE) AS context_runs_today,
                        (SELECT COUNT(*) FROM capital_brain_runs WHERE created_at::date = CURRENT_DATE) AS capital_runs_today,
                        (SELECT COUNT(*) FROM context_brain_outputs WHERE insufficient_data IS TRUE) +
                        (SELECT COUNT(*) FROM capital_brain_outputs WHERE insufficient_data IS TRUE) AS insufficient_data_count,
                        (SELECT COUNT(*) FROM capital_brain_outputs WHERE capital_allowed IS FALSE) AS capital_blocked_count,
                        (SELECT AVG(confidence) FROM context_brain_outputs) AS average_context_confidence,
                        (SELECT AVG(allocation_confidence) FROM capital_brain_outputs) AS average_allocation_confidence,
                        GREATEST(
                            COALESCE((SELECT MAX(created_at) FROM context_brain_outputs), 'epoch'::timestamptz),
                            COALESCE((SELECT MAX(created_at) FROM capital_brain_outputs), 'epoch'::timestamptz)
                        ) AS latest_brain_update
                    """
                ).fetchone()
                latest_context = conn.execute("SELECT market_id, context_shift, direction, strength, confidence, created_at FROM context_brain_outputs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
                latest_capital = conn.execute("SELECT market_id, capital_allowed, block_reason, allocation_confidence, created_at FROM capital_brain_outputs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
                shifts = conn.execute("SELECT market_id, direction, strength, confidence, risks_json, created_at FROM context_brain_outputs WHERE context_shift IS TRUE ORDER BY strength DESC, confidence DESC LIMIT 5").fetchall()
                blocks = conn.execute("SELECT market_id, candidate_engine, block_reason, allocation_confidence, created_at FROM capital_brain_outputs WHERE capital_allowed IS FALSE ORDER BY created_at DESC LIMIT 5").fetchall()
                risks = conn.execute(
                    """
                    SELECT value AS risk, COUNT(*) AS count
                    FROM context_brain_outputs, jsonb_array_elements_text(risks_json)
                    GROUP BY value
                    ORDER BY count DESC
                    LIMIT 5
                    """
                ).fetchall()
                block_reasons = conn.execute(
                    """
                    SELECT COALESCE(block_reason, 'none') AS block_reason, COUNT(*) AS count
                    FROM capital_brain_outputs
                    WHERE capital_allowed IS FALSE
                    GROUP BY COALESCE(block_reason, 'none')
                    ORDER BY count DESC
                    LIMIT 5
                    """
                ).fetchall()
            return {
                "brain_status": "OK" if int((stats or {}).get("context_runs_today") or 0) or int((stats or {}).get("capital_runs_today") or 0) else "EMPTY",
                "context_runs_today": int((stats or {}).get("context_runs_today") or 0),
                "capital_runs_today": int((stats or {}).get("capital_runs_today") or 0),
                "latest_context_shift": _row_dict(latest_context),
                "latest_capital_allowed": _row_dict(latest_capital),
                "insufficient_data_count": int((stats or {}).get("insufficient_data_count") or 0),
                "capital_blocked_count": int((stats or {}).get("capital_blocked_count") or 0),
                "top_context_shifts": [_row_dict(row) for row in shifts],
                "top_capital_blocks": [_row_dict(row) for row in blocks],
                "average_context_confidence": _float_or_none((stats or {}).get("average_context_confidence")),
                "average_allocation_confidence": _float_or_none((stats or {}).get("average_allocation_confidence")),
                "common_context_risks": [_row_dict(row) for row in risks],
                "common_capital_block_reasons": [_row_dict(row) for row in block_reasons],
                "latest_brain_update": _iso_or_none((stats or {}).get("latest_brain_update")),
                "errors": [],
            }
        except Exception as exc:
            empty["brain_status"] = "ERROR"
            empty["errors"] = [str(exc)]
            return empty

    def _market_memory_overview(self) -> dict[str, object]:
        empty = {
            "memory_status": "DISABLED" if not self._factory.enabled else "EMPTY",
            "last_memory_update": None,
            "market_memories_count": 0,
            "family_memories_count": 0,
            "engine_memories_count": 0,
            "source_memories_count": 0,
            "whale_memories_count": 0,
            "insufficient_data_count": 0,
            "top_market_families_by_confidence": [],
            "best_engine_by_family": [],
            "worst_slippage_families": [],
            "highest_wording_risk_families": [],
            "top_reliable_sources": [],
            "top_whales_by_memory_score": [],
            "no_trade_regret_rate": None,
            "recent_memory_updates": [],
            "errors": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass('market_memory_v2') AS name").fetchone()
                if exists is None or exists["name"] is None:
                    return empty
                counts = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM market_memory_v2) AS market_memories_count,
                        (SELECT COUNT(*) FROM market_family_memory) AS family_memories_count,
                        (SELECT COUNT(*) FROM engine_performance_memory) AS engine_memories_count,
                        (SELECT COUNT(*) FROM source_reliability_memory) AS source_memories_count,
                        (SELECT COUNT(*) FROM whale_memory) AS whale_memories_count,
                        (SELECT COUNT(*) FROM market_memory_v2 WHERE memory_status = 'insufficient_data') AS insufficient_data_count,
                        (SELECT MAX(updated_at) FROM market_memory_v2) AS last_memory_update
                    """
                ).fetchone()
                families = conn.execute(
                    """
                    SELECT market_family, memory_confidence, observations_count, best_engine
                    FROM market_family_memory
                    ORDER BY memory_confidence DESC, observations_count DESC, updated_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                engines = conn.execute(
                    """
                    SELECT market_family, best_engine, best_engine_confidence, observations_count
                    FROM market_family_memory
                    ORDER BY best_engine_confidence DESC, observations_count DESC
                    LIMIT 5
                    """
                ).fetchall()
                slippage = conn.execute(
                    """
                    SELECT market_family, slippage_risk_score, avg_expected_slippage_bps, avg_realized_slippage_bps, confidence
                    FROM slippage_memory
                    ORDER BY slippage_risk_score DESC, confidence DESC, updated_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                rules = conn.execute(
                    """
                    SELECT market_family, avg_wording_risk, avg_dispute_risk, rules_risk_score, confidence
                    FROM rules_risk_memory
                    ORDER BY rules_risk_score DESC, confidence DESC, updated_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                sources = conn.execute(
                    """
                    SELECT source_type, source_name, reliability_score, usefulness_score, confidence
                    FROM source_reliability_memory
                    ORDER BY reliability_score DESC, usefulness_score DESC, updated_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                whales = conn.execute(
                    """
                    SELECT whale_id, market_family, whale_score, follow_value_avg, noise_score_avg, confidence
                    FROM whale_memory
                    ORDER BY whale_score DESC, confidence DESC, updated_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                no_trade = conn.execute(
                    """
                    SELECT AVG(regret_rate) AS no_trade_regret_rate
                    FROM no_trade_memory
                    WHERE observations_count > 0
                    """
                ).fetchone()
                recent = conn.execute(
                    """
                    SELECT market_id, market_family, memory_status, memory_confidence, updated_at
                    FROM market_memory_v2
                    ORDER BY updated_at DESC
                    LIMIT 5
                    """
                ).fetchall()
            return {
                "memory_status": "OK" if int((counts or {}).get("market_memories_count") or 0) else "EMPTY",
                "last_memory_update": _iso_or_none((counts or {}).get("last_memory_update")),
                "market_memories_count": int((counts or {}).get("market_memories_count") or 0),
                "family_memories_count": int((counts or {}).get("family_memories_count") or 0),
                "engine_memories_count": int((counts or {}).get("engine_memories_count") or 0),
                "source_memories_count": int((counts or {}).get("source_memories_count") or 0),
                "whale_memories_count": int((counts or {}).get("whale_memories_count") or 0),
                "insufficient_data_count": int((counts or {}).get("insufficient_data_count") or 0),
                "top_market_families_by_confidence": [_row_dict(row) for row in families],
                "best_engine_by_family": [_row_dict(row) for row in engines],
                "worst_slippage_families": [_row_dict(row) for row in slippage],
                "highest_wording_risk_families": [_row_dict(row) for row in rules],
                "top_reliable_sources": [_row_dict(row) for row in sources],
                "top_whales_by_memory_score": [_row_dict(row) for row in whales],
                "no_trade_regret_rate": _float_or_none((no_trade or {}).get("no_trade_regret_rate")),
                "recent_memory_updates": [_row_dict(row) for row in recent],
                "errors": [],
            }
        except Exception as exc:
            empty["memory_status"] = "ERROR"
            empty["errors"] = [str(exc)]
            return empty

    def _market_technical_overview(self) -> dict[str, object]:
        empty = {
            "technical_neuron_status": "DISABLED" if not self._factory.enabled else "EMPTY",
            "signals_today": 0,
            "blocked_today": 0,
            "stale_orderbooks": 0,
            "average_spread_bps": None,
            "average_exit_quality": None,
            "average_slippage_bps": None,
            "average_time_efficiency": None,
            "top_technical_markets": [],
            "recent_block_reasons": [],
            "latest_signal_ts": None,
            "errors": 0,
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                stats = conn.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) AS signals_today,
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND technical_blocked IS TRUE) AS blocked_today,
                        MAX(ts) AS latest_signal_ts
                    FROM market_technical_signals
                    """
                ).fetchone()
                orderbook = conn.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE stale IS TRUE) AS stale_orderbooks,
                        AVG(spread_bps) AS average_spread_bps
                    FROM orderbook_signals
                    """
                ).fetchone()
                liquidity = conn.execute("SELECT AVG(exit_quality_score) AS average_exit_quality, AVG(expected_slippage_bps) AS average_slippage_bps FROM liquidity_signals").fetchone()
                time_row = conn.execute("SELECT AVG(time_efficiency_score) AS average_time_efficiency FROM time_signals").fetchone()
                top = conn.execute(
                    """
                    SELECT market_id, technical_score, data_completeness_score, market_regime, ts
                    FROM market_technical_signals
                    WHERE technical_blocked IS FALSE AND stale IS FALSE AND data_completeness_score >= 0.5
                    ORDER BY technical_score DESC, ts DESC
                    LIMIT 5
                    """
                ).fetchall()
                blocked = conn.execute(
                    """
                    SELECT market_id, block_reasons_json, ts
                    FROM market_technical_signals
                    WHERE technical_blocked IS TRUE
                    ORDER BY ts DESC
                    LIMIT 5
                    """
                ).fetchall()
            return {
                "technical_neuron_status": "OK" if (stats or {}).get("latest_signal_ts") else "EMPTY",
                "signals_today": int((stats or {}).get("signals_today") or 0),
                "blocked_today": int((stats or {}).get("blocked_today") or 0),
                "stale_orderbooks": int((orderbook or {}).get("stale_orderbooks") or 0),
                "average_spread_bps": _float_or_none((orderbook or {}).get("average_spread_bps")),
                "average_exit_quality": _float_or_none((liquidity or {}).get("average_exit_quality")),
                "average_slippage_bps": _float_or_none((liquidity or {}).get("average_slippage_bps")),
                "average_time_efficiency": _float_or_none((time_row or {}).get("average_time_efficiency")),
                "top_technical_markets": [_row_dict(row) for row in top],
                "recent_block_reasons": [_row_dict(row) for row in blocked],
                "latest_signal_ts": _iso_or_none((stats or {}).get("latest_signal_ts")),
                "errors": 0,
            }
        except Exception:
            empty["technical_neuron_status"] = "ERROR"
            empty["errors"] = 1
            return empty

    def _whale_neuron_overview(self) -> dict[str, object]:
        empty = {
            "whale_neuron_health": "DISABLED" if not self._factory.enabled else "EMPTY",
            "whale_events_today": 0,
            "active_whales": 0,
            "copy_worthy_whales": 0,
            "noisy_whales": 0,
            "top_whale_market_scores": [],
            "top_follow_value_whales": [],
            "average_whale_noise": 0.0,
            "whale_reversal_risk_count": 0,
            "latest_whale_event_at": None,
            "whale_errors_today": 0,
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                events = conn.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE event_time::date = CURRENT_DATE) AS events_today,
                        MAX(event_time) AS latest_event_at
                    FROM whale_events
                    """
                ).fetchone()
                registry = conn.execute(
                    """
                    SELECT COUNT(*) FILTER (WHERE COALESCE(status, registry_status) IN ('ACTIVE','WATCHLIST')) AS active_whales
                    FROM whale_registry
                    """
                ).fetchone()
                categories = conn.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE category = 'copy_worthy_whale' AND active = true) AS copy_worthy,
                        COUNT(*) FILTER (WHERE category = 'noisy_whale' AND active = true) AS noisy
                    FROM whale_categories
                    """
                ).fetchone()
                scores = conn.execute(
                    """
                    SELECT market_id, whale_id, follow_value, noise_penalty, whale_reversal_risk, confidence, signal_json
                    FROM whale_market_scores
                    ORDER BY follow_value DESC, whale_presence_score DESC, computed_at DESC NULLS LAST, created_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                profiles = conn.execute(
                    """
                    SELECT whale_id, follow_value, noise_score, timing_quality, copy_worthy_score, sample_size
                    FROM whale_profiles
                    ORDER BY follow_value DESC, created_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                aggregate = conn.execute(
                    """
                    SELECT
                        COALESCE(AVG(noise_score), 0) AS avg_noise,
                        COUNT(*) FILTER (WHERE reversal_risk_score >= 0.6) AS reversal_risk_count
                    FROM whale_profiles
                    """
                ).fetchone()
                source_errors = conn.execute(
                    """
                    SELECT COALESCE(SUM(error_count) FILTER (WHERE last_error_at::date = CURRENT_DATE), 0) AS errors_today
                    FROM whale_sources
                    """
                ).fetchone()
            return {
                "whale_neuron_health": "OK",
                "whale_events_today": int((events or {}).get("events_today") or 0),
                "active_whales": int((registry or {}).get("active_whales") or 0),
                "copy_worthy_whales": int((categories or {}).get("copy_worthy") or 0),
                "noisy_whales": int((categories or {}).get("noisy") or 0),
                "top_whale_market_scores": [_row_dict(row) for row in scores],
                "top_follow_value_whales": [_row_dict(row) for row in profiles],
                "average_whale_noise": float((aggregate or {}).get("avg_noise") or 0),
                "whale_reversal_risk_count": int((aggregate or {}).get("reversal_risk_count") or 0),
                "latest_whale_event_at": (events or {}).get("latest_event_at"),
                "whale_errors_today": int((source_errors or {}).get("errors_today") or 0),
            }
        except Exception as exc:
            empty["whale_neuron_health"] = "ERROR"
            empty["error"] = str(exc)
            return empty

    def _social_neuron_overview(self) -> dict[str, object]:
        empty = {
            "social_feed_health": "DISABLED" if not self._factory.enabled else "EMPTY",
            "social_sources_enabled": 0,
            "social_events_today": 0,
            "latest_social_at": None,
            "top_hype_markets": [],
            "top_narratives": [],
            "social_market_links_today": 0,
            "average_bot_risk": 0.0,
            "average_spam_ratio": 0.0,
            "social_ai_calls_today": 0,
            "social_errors_today": 0,
            "social_lead_lag_summary": {"status": "INSUFFICIENT_DATA"},
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                sources = conn.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE enabled = true) AS enabled_count,
                        COALESCE(SUM(error_count) FILTER (WHERE last_error_at::date = CURRENT_DATE), 0) AS errors_today
                    FROM social_sources
                    """
                ).fetchone()
                events = conn.execute(
                    """
                    SELECT COUNT(*) AS events_today, MAX(collected_at) AS latest_social_at, AVG(bot_risk) AS avg_bot
                    FROM social_normalized_events
                    WHERE collected_at::date = CURRENT_DATE
                    """
                ).fetchone()
                links = conn.execute("SELECT COUNT(*) AS count FROM social_market_links WHERE created_at::date = CURRENT_DATE").fetchone()
                hype = conn.execute(
                    """
                    SELECT market_id, hype_pressure, mentions_velocity, bot_risk, spam_ratio, confidence, computed_at
                    FROM social_hype_scores
                    ORDER BY hype_pressure DESC, confidence DESC, computed_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                narratives = conn.execute(
                    """
                    SELECT narrative_id, title, event_count, narrative_strength, confidence, status, last_seen_at
                    FROM social_narratives
                    ORDER BY narrative_strength DESC, last_seen_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                spam = conn.execute("SELECT AVG(spam_ratio) AS avg_spam FROM social_hype_scores WHERE computed_at::date = CURRENT_DATE").fetchone()
                ai_events = conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'social.ai.analyzed' AND stored_at::date = CURRENT_DATE").fetchone()
            enabled_count = int(sources["enabled_count"] or 0)
            errors_today = int(sources["errors_today"] or 0)
            return {
                "social_feed_health": "HEALTHY" if enabled_count and errors_today == 0 else "DEGRADED" if enabled_count else "EMPTY",
                "social_sources_enabled": enabled_count,
                "social_events_today": int(events["events_today"] or 0),
                "latest_social_at": _iso_or_none(events["latest_social_at"]),
                "top_hype_markets": [_row_dict(row) for row in hype],
                "top_narratives": [_row_dict(row) for row in narratives],
                "social_market_links_today": int(links["count"] or 0),
                "average_bot_risk": float(events["avg_bot"] or 0),
                "average_spam_ratio": float(spam["avg_spam"] or 0),
                "social_ai_calls_today": int(ai_events["count"] or 0),
                "social_errors_today": errors_today,
                "social_lead_lag_summary": {"status": "INSUFFICIENT_DATA"},
            }
        except Exception:
            return empty

    def _rules_neuron_overview(self) -> dict[str, object]:
        empty = {
            "rules_coverage_pct": 0.0,
            "markets_with_rules_analysis": 0,
            "missing_rules_count": 0,
            "high_wording_risk_count": 0,
            "high_dispute_risk_count": 0,
            "compliance_block_count": 0,
            "average_resolution_clarity": 0.0,
            "latest_rules_analysis_at": None,
            "top_compliance_blocks": [],
            "top_wording_risk_markets": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                row = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM markets_v2) AS total_markets,
                        (SELECT COUNT(DISTINCT market_id) FROM market_rules WHERE rules_text IS NOT NULL AND rules_text <> '') AS markets_with_rules,
                        (SELECT COUNT(DISTINCT market_id) FROM rules_analysis) AS markets_with_rules_analysis,
                        (SELECT COUNT(*) FROM market_rules WHERE rules_text IS NULL OR rules_text = '') AS missing_rules_count,
                        (SELECT COUNT(*) FROM rules_analysis WHERE wording_risk >= 0.75) AS high_wording_risk_count,
                        (SELECT COUNT(*) FROM rules_analysis WHERE dispute_risk >= 0.75) AS high_dispute_risk_count,
                        (SELECT COUNT(*) FROM compliance_blocks WHERE active = true) AS compliance_block_count,
                        (SELECT AVG(resolution_clarity) FROM rules_analysis) AS average_resolution_clarity,
                        (SELECT MAX(created_at) FROM rules_analysis) AS latest_rules_analysis_at
                    """
                ).fetchone()
                top_blocks = conn.execute(
                    """
                    SELECT market_id, block_type, severity, reason, created_at
                    FROM compliance_blocks
                    WHERE active = true
                    ORDER BY created_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                top_risk = conn.execute(
                    """
                    SELECT market_id, wording_risk, dispute_risk, resolution_clarity, recommendation, created_at
                    FROM rules_analysis
                    ORDER BY wording_risk DESC, created_at DESC
                    LIMIT 5
                    """
                ).fetchall()
            total = int(row["total_markets"] or 0)
            return {
                "rules_coverage_pct": _pct(row["markets_with_rules"], total),
                "markets_with_rules_analysis": int(row["markets_with_rules_analysis"] or 0),
                "missing_rules_count": int(row["missing_rules_count"] or 0),
                "high_wording_risk_count": int(row["high_wording_risk_count"] or 0),
                "high_dispute_risk_count": int(row["high_dispute_risk_count"] or 0),
                "compliance_block_count": int(row["compliance_block_count"] or 0),
                "average_resolution_clarity": float(row["average_resolution_clarity"] or 0),
                "latest_rules_analysis_at": _iso_or_none(row["latest_rules_analysis_at"]),
                "top_compliance_blocks": [_row_dict(item) for item in top_blocks],
                "top_wording_risk_markets": [_row_dict(item) for item in top_risk],
            }
        except Exception:
            return empty

    def _news_neuron_overview(self) -> dict[str, object]:
        empty = {
            "news_feed_health": "DISABLED" if not self._factory.enabled else "EMPTY",
            "news_sources_enabled": 0,
            "news_events_today": 0,
            "latest_news_at": None,
            "latest_breaking_news": None,
            "top_news_market_links": [],
            "top_news_impact_scores": [],
            "source_reliability_summary": [],
            "news_ai_calls_today": 0,
            "news_latency_seconds": None,
            "news_errors_today": 0,
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                sources = conn.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE enabled = true) AS enabled_count,
                        COALESCE(SUM(error_count) FILTER (WHERE last_error_at::date = CURRENT_DATE), 0) AS errors_today
                    FROM news_sources
                    """
                ).fetchone()
                events = conn.execute(
                    """
                    SELECT COUNT(*) AS events_today, MAX(collected_at) AS latest_news_at
                    FROM news_normalized_events
                    WHERE collected_at::date = CURRENT_DATE
                    """
                ).fetchone()
                latest = conn.execute(
                    """
                    SELECT news_event_id, title, category, urgency_score, importance_score, collected_at
                    FROM news_normalized_events
                    ORDER BY urgency_score DESC, importance_score DESC, collected_at DESC
                    LIMIT 1
                    """
                ).fetchone()
                top_links = conn.execute(
                    """
                    SELECT news_event_id, market_id, link_score, confidence, direction, link_reason
                    FROM news_market_links
                    ORDER BY link_score DESC, confidence DESC, created_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                top_impacts = conn.execute(
                    """
                    SELECT impact_id, news_event_id, market_id, direction, strength, confidence, ttl_seconds
                    FROM news_impact_scores
                    ORDER BY strength DESC, confidence DESC, created_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                reliability = conn.execute(
                    """
                    SELECT source_id, category, reliability_score, total_events, linked_events, error_count
                    FROM news_source_reliability
                    ORDER BY last_updated_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                ai_calls = conn.execute(
                    "SELECT COUNT(*) AS count FROM news_ai_analysis WHERE created_at::date = CURRENT_DATE"
                ).fetchone()
            enabled_count = int(sources["enabled_count"] or 0)
            event_count = int(events["events_today"] or 0)
            return {
                "news_feed_health": "HEALTHY" if enabled_count and int(sources["errors_today"] or 0) == 0 else "DEGRADED" if enabled_count else "EMPTY",
                "news_sources_enabled": enabled_count,
                "news_events_today": event_count,
                "latest_news_at": _iso_or_none(events["latest_news_at"]),
                "latest_breaking_news": _row_dict(latest),
                "top_news_market_links": [_row_dict(row) for row in top_links],
                "top_news_impact_scores": [_row_dict(row) for row in top_impacts],
                "source_reliability_summary": [_row_dict(row) for row in reliability],
                "news_ai_calls_today": int(ai_calls["count"] or 0),
                "news_latency_seconds": None,
                "news_errors_today": int(sources["errors_today"] or 0),
            }
        except Exception:
            return empty

    def _ai_brain_overview(self) -> dict[str, object]:
        empty = {
            "local_ai_status": "UNAVAILABLE",
            "cloud_ai_enabled": False,
            "cloud_calls_today": 0,
            "local_calls_today": 0,
            "ai_cost_today": 0.0,
            "ai_cache_hit_rate": 0.0,
            "ai_escalations_today": 0,
            "ai_errors_today": 0,
            "last_ai_decision_at": None,
            "top_ai_task_types": [],
            "model_performance_summary": [],
        }
        if not self._factory.enabled:
            return empty
        try:
            with self._factory.connect() as conn:
                costs = conn.execute(
                    """
                    SELECT
                        COALESCE(SUM(estimated_cost), 0) AS ai_cost_today,
                        COUNT(*) FILTER (WHERE provider = 'cloud') AS cloud_calls_today,
                        COUNT(*) FILTER (WHERE provider = 'local') AS local_calls_today
                    FROM ai_cost_ledger
                    WHERE created_at::date = CURRENT_DATE
                    """
                ).fetchone()
                cache = conn.execute(
                    "SELECT COALESCE(SUM(hit_count), 0) AS hits, COUNT(*) AS entries FROM ai_cache"
                ).fetchone()
                escalations = conn.execute(
                    "SELECT COUNT(*) AS count FROM ai_escalations WHERE created_at::date = CURRENT_DATE"
                ).fetchone()
                errors = conn.execute(
                    "SELECT COUNT(*) AS count FROM ai_requests WHERE status = 'FAILED' AND created_at::date = CURRENT_DATE"
                ).fetchone()
                last_decision = conn.execute("SELECT MAX(created_at) AS last_at FROM ai_decision_logs").fetchone()
                top_tasks = conn.execute(
                    """
                    SELECT task_type, COUNT(*) AS count
                    FROM ai_requests
                    GROUP BY task_type
                    ORDER BY count DESC
                    LIMIT 5
                    """
                ).fetchall()
                performance = conn.execute(
                    """
                    SELECT model_name, provider, task_type, total_requests, failures, estimated_total_cost, usefulness_score
                    FROM ai_model_performance
                    ORDER BY last_updated_at DESC
                    LIMIT 5
                    """
                ).fetchall()
            hits = int(cache["hits"] or 0)
            entries = int(cache["entries"] or 0)
            return {
                "local_ai_status": "RECORDED" if int(costs["local_calls_today"] or 0) else "UNAVAILABLE",
                "cloud_ai_enabled": False,
                "cloud_calls_today": int(costs["cloud_calls_today"] or 0),
                "local_calls_today": int(costs["local_calls_today"] or 0),
                "ai_cost_today": float(costs["ai_cost_today"] or 0),
                "ai_cache_hit_rate": round(hits / max(hits + entries, 1), 4),
                "ai_escalations_today": int(escalations["count"] or 0),
                "ai_errors_today": int(errors["count"] or 0),
                "last_ai_decision_at": _iso_or_none(last_decision["last_at"]),
                "top_ai_task_types": [_row_dict(row) for row in top_tasks],
                "model_performance_summary": [_row_dict(row) for row in performance],
            }
        except Exception:
            return empty

    def _data_foundation_overview(self) -> dict[str, object]:
        if not self._factory.enabled:
            return {
                "market_count": 0,
                "active_market_count": 0,
                "tradable_market_count": 0,
                "orderbook_coverage_pct": 0.0,
                "rules_coverage_pct": 0.0,
                "liquidity_coverage_pct": 0.0,
                "stale_market_count": 0,
                "closed_market_count": 0,
                "average_data_completeness": 0.0,
                "last_market_snapshot_at": None,
                "last_orderbook_snapshot_at": None,
            }
        try:
            with self._factory.connect() as conn:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS market_count,
                        COUNT(*) FILTER (WHERE active = true) AS active_market_count,
                        COUNT(*) FILTER (WHERE accepting_orders = true AND closed = false) AS tradable_market_count,
                        COUNT(*) FILTER (WHERE closed = true) AS closed_market_count
                    FROM markets_v2
                    """
                ).fetchone()
                coverage = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(DISTINCT market_id) FROM market_rules WHERE rules_text IS NOT NULL AND rules_text <> '') AS rules_count,
                        (SELECT COUNT(DISTINCT market_id) FROM orderbook_snapshots) AS orderbook_count,
                        (SELECT COUNT(DISTINCT market_id) FROM liquidity_snapshots) AS liquidity_count,
                        (SELECT COUNT(*) FROM market_snapshots_v2 WHERE stale = true) AS stale_market_count,
                        (SELECT AVG(data_completeness_score) FROM market_snapshots_v2) AS average_data_completeness,
                        (SELECT MAX(snapshot_at) FROM market_snapshots_v2) AS last_market_snapshot_at,
                        (SELECT MAX(snapshot_at) FROM orderbook_snapshots) AS last_orderbook_snapshot_at
                    """
                ).fetchone()
            total = int(row["market_count"] or 0)
            return {
                "market_count": total,
                "active_market_count": int(row["active_market_count"] or 0),
                "tradable_market_count": int(row["tradable_market_count"] or 0),
                "orderbook_coverage_pct": _pct(coverage["orderbook_count"], total),
                "rules_coverage_pct": _pct(coverage["rules_count"], total),
                "liquidity_coverage_pct": _pct(coverage["liquidity_count"], total),
                "stale_market_count": int(coverage["stale_market_count"] or 0),
                "closed_market_count": int(row["closed_market_count"] or 0),
                "average_data_completeness": float(coverage["average_data_completeness"] or 0),
                "last_market_snapshot_at": _iso_or_none(coverage["last_market_snapshot_at"]),
                "last_orderbook_snapshot_at": _iso_or_none(coverage["last_orderbook_snapshot_at"]),
            }
        except Exception:
            return {
                "market_count": 0,
                "active_market_count": 0,
                "tradable_market_count": 0,
                "orderbook_coverage_pct": 0.0,
                "rules_coverage_pct": 0.0,
                "liquidity_coverage_pct": 0.0,
                "stale_market_count": 0,
                "closed_market_count": 0,
                "average_data_completeness": 0.0,
                "last_market_snapshot_at": None,
                "last_orderbook_snapshot_at": None,
            }

    def _event_bus_overview(self) -> dict[str, object]:
        if not self._factory.enabled:
            return {
                "event_bus_health": "DISABLED",
                "events_per_minute": 0.0,
                "failed_event_count": 0,
                "dlq_count": 0,
                "open_dlq_count": 0,
                "consumer_count": 0,
                "last_event_time": None,
                "replay_jobs_running": 0,
                "event_store_status": "DISABLED",
            }
        try:
            repository = EventStoreRepository()
            with self._factory.connect() as conn:
                metrics = repository.get_event_lag(conn)
                metrics["replay_jobs_running"] = repository.replay_jobs_running(conn)
            last_event_time = metrics.get("last_event_time")
            return {
                "event_bus_health": "HEALTHY" if metrics.get("open_dlq_count", 0) == 0 else "DEGRADED",
                "events_per_minute": metrics.get("events_per_minute", 0.0),
                "failed_event_count": metrics.get("failed_events", 0),
                "dlq_count": metrics.get("dlq_count", 0),
                "open_dlq_count": metrics.get("open_dlq_count", 0),
                "consumer_count": metrics.get("consumer_count", 0),
                "last_event_time": last_event_time.isoformat() if isinstance(last_event_time, datetime) else last_event_time,
                "replay_jobs_running": metrics.get("replay_jobs_running", 0),
                "event_store_status": "HEALTHY",
            }
        except Exception:
            return {
                "event_bus_health": "ERROR",
                "events_per_minute": 0.0,
                "failed_event_count": 0,
                "dlq_count": 0,
                "open_dlq_count": 0,
                "consumer_count": 0,
                "last_event_time": None,
                "replay_jobs_running": 0,
                "event_store_status": "ERROR",
            }


def _row_dict(row: dict[str, object] | None) -> dict[str, object] | None:
    if row is None:
        return None
    output: dict[str, object] = {}
    for key, value in dict(row).items():
        if isinstance(value, Decimal):
            output[key] = float(value)
        elif isinstance(value, datetime):
            output[key] = value.isoformat()
        else:
            output[key] = value
    return output


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _pct(numerator: object, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((float(numerator or 0) / denominator) * 100, 2)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _freshness_status(value: datetime | None, *, stale_after_seconds: int) -> str:
    if value is None:
        return "ABSENT"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return "ABSENT"
    age = datetime.now(UTC) - value
    if age <= timedelta(seconds=stale_after_seconds):
        return "FRESH"
    return "STALE"


def _iso_or_none(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None if value is None else str(value)
