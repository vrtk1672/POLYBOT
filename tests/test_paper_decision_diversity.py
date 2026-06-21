from __future__ import annotations

from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.paper_runtime_decisions import PaperRuntimeDecisionService


def test_decision_selector_groups_by_market_and_side(postgres_test_schema) -> None:
    _prepare()
    _seed_review("market-a", "YES", score=72, duplicate_suffix="best")
    _seed_review("market-a", "YES", score=70, duplicate_suffix="duplicate")
    _seed_review("market-b", "NO", score=65, duplicate_suffix="best")
    _seed_review("market-c", "YES", score=62, duplicate_suffix="best")

    result = PaperRuntimeDecisionService().refresh(limit=10, force=True)

    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute(
            """
            SELECT market_id, side, decision, duplicate_suppressed_count, is_current_batch
            FROM paper_runtime_decisions
            WHERE is_current_batch IS TRUE
            ORDER BY market_id, side
            """
        ).fetchall()

    pairs = {(row["market_id"], row["side"]) for row in rows}
    assert result["unique_market_count"] == 3
    assert result["unique_market_side_count"] == 3
    assert result["duplicate_suppressed_count"] == 1
    assert pairs == {("market-a", "YES"), ("market-b", "NO"), ("market-c", "YES")}
    assert sum(1 for row in rows if row["market_id"] == "market-a" and row["side"] == "YES") == 1


def test_open_exposure_duplicate_blocker_remains_active(postgres_test_schema) -> None:
    _prepare()
    _seed_review("market-open", "YES", score=72, duplicate_suffix="best")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_positions (
                paper_run_id, market_id, intended_outcome, size, avg_entry,
                mark_price, current_status, opened_at, updated_at
            )
            VALUES ('run-open', 'market-open', 'YES', 1, 0.5, 0.5, 'OPEN', now(), now())
            """
        )

    PaperRuntimeDecisionService().refresh(limit=10, force=True)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT decision, paper_enter_allowed, blockers_json
            FROM paper_runtime_decisions
            WHERE market_id='market-open' AND side='YES' AND is_current_batch IS TRUE
            """
        ).fetchone()

    assert row["decision"] == "BLOCK"
    assert row["paper_enter_allowed"] is False
    assert "DUPLICATE_OPEN_PAPER_EXPOSURE" in row["blockers_json"]


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_runtime_decision_runs",
            "paper_runtime_decisions",
            "paper_observation_policy_reviews",
            "paper_positions",
            "paper_intents",
            "orderbook_snapshots",
            "research_priority_watchlist",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _seed_review(market_id: str, side: str, *, score: int, duplicate_suffix: str) -> None:
    now = datetime.now(UTC)
    token_id = f"{market_id}-{side.lower()}-token"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid,
                best_ask, spread, mid_price, liquidity_score, source,
                snapshot_status, is_stale, snapshot_at, collected_at, created_at
            )
            VALUES (%s,%s,%s,%s,0.50,0.52,0.02,0.51,0.8,'test','OK',false,%s,%s,%s)
            """,
            (
                f"book-{market_id}-{side}-{duplicate_suffix}",
                market_id,
                token_id,
                side,
                now - timedelta(seconds=5),
                now - timedelta(seconds=5),
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO research_priority_watchlist (
                research_watchlist_id, priority_run_id, market_id, condition_id,
                priority_band, priority_score, refresh_cadence_seconds,
                market_status, token_verification_state, liquidity_state,
                spread_state, volume_state, movement_state, payout_odds_state,
                priority_reasons_json, demotion_reasons_json, required_to_upgrade_json,
                score_components_json, evidence_inputs_json, scheduler_state
            )
            VALUES (%s,'run',%s,%s,'HIGH',80,300,'ACTIVE','TOKENS_VERIFIED',
                    'GOOD','TIGHT','HIGH','ACTIVE','AVAILABLE',
                    '[]'::jsonb,'[]'::jsonb,'[]'::jsonb,'{}'::jsonb,'{}'::jsonb,'DUE')
            ON CONFLICT DO NOTHING
            """,
            (f"watch-{market_id}", market_id, f"condition-{market_id}"),
        )
        conn.execute(
            """
            INSERT INTO paper_observation_policy_reviews (
                paper_observation_policy_review_id, source_type,
                proactive_candidate_seed_id, seed_mesh_inquiry_id, adapter_payload_id,
                opportunity_score_id, market_id, condition_id, side, token_id,
                observation_policy_state, decision_band, opportunity_score,
                edge_state, thesis_state, risk_state, capital_state, exit_state,
                lifecycle_state, orderbook_state, token_verification_state,
                candidate_event_scope_state, lineage_state,
                observation_allowed_by_policy, data_only,
                observation_policy_review_only, execution_allowed, paper_allowed,
                shadow_allowed, live_allowed, max_observation_notional,
                max_open_positions, time_stop_seconds, hard_blockers_json,
                soft_blockers_json, policy_blockers_json, required_to_pass_json,
                lineage_json, limits_json, metadata_json, policy_reason,
                updated_at
            )
            VALUES (
                %s,'PROACTIVE_SEED_MESH',%s,%s,%s,%s,%s,%s,%s,%s,
                'OBSERVATION_POLICY_ELIGIBLE','PAPER_OBSERVATION',%s,
                'EDGE_SUPPORTED','THESIS_SUPPORTED','RISK_OK','CAPITAL_WATCH','EXIT_READY',
                'DATA_ONLY_RESEARCH','FRESH','TOKENS_VERIFIED',
                'CANDIDATE_SCOPED','COMPLETE',
                true,true,true,false,false,false,false,5,
                1,3600,'[]'::jsonb,%s,'[]'::jsonb,'[]'::jsonb,
                %s,'{}'::jsonb,'{}'::jsonb,'test policy review', %s
            )
            """,
            (
                f"review-{market_id}-{side}-{duplicate_suffix}",
                f"seed-{market_id}-{side}-{duplicate_suffix}",
                f"inq-{market_id}-{side}-{duplicate_suffix}",
                f"payload-{market_id}-{side}-{duplicate_suffix}",
                f"score-{market_id}-{side}-{duplicate_suffix}",
                market_id,
                f"condition-{market_id}",
                side,
                token_id,
                score,
                Jsonb(["capital_watch_not_full_paper_ready"]),
                Jsonb({"source_event_id": f"event-{market_id}", "proactive_candidate_seed_id": f"seed-{market_id}-{side}-{duplicate_suffix}"}),
                now,
            ),
        )


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])
