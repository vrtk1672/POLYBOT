from __future__ import annotations

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.paper_runtime_decisions import PaperRuntimeDecisionService


def test_decision_service_emits_watch_and_block_rows_for_non_enterable_policy_inputs(postgres_test_schema) -> None:
    _prepare()
    _seed_policy_review(
        review_id="review-eligible",
        market_id="691547",
        side="YES",
        state="OBSERVATION_POLICY_ELIGIBLE",
        decision_band="PAPER_OBSERVATION",
        score=61.99,
        thesis_state="THESIS_SUPPORTED",
        orderbook_state="FRESH",
        token_state="TOKENS_VERIFIED",
        policy_blockers=[],
        allowed=True,
    )
    _seed_policy_review(
        review_id="review-watch",
        market_id="597967",
        side="NO",
        state="OBSERVATION_POLICY_WATCH",
        decision_band="HARD_BLOCKED",
        score=55.46,
        thesis_state="THESIS_WATCH",
        orderbook_state="FRESH",
        token_state="TOKENS_VERIFIED",
        policy_blockers=["thesis_watch_not_observation_policy_eligible", "existing_hard_blockers_present"],
        allowed=False,
    )
    _seed_policy_review(
        review_id="review-incomplete",
        market_id="666655",
        side="YES",
        state="OBSERVATION_POLICY_INCOMPLETE",
        decision_band="HARD_BLOCKED",
        score=46.3,
        thesis_state="THESIS_MISSING",
        exit_state="EXIT_NOT_READY",
        orderbook_state="FRESH",
        token_state="TOKENS_VERIFIED",
        policy_blockers=["thesis_not_supported", "exit_not_ready"],
        allowed=False,
    )

    result = PaperRuntimeDecisionService().refresh(limit=10, force=True)

    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute(
            """
            SELECT market_id, side, decision, paper_enter_allowed, blockers_json, warnings_json
            FROM paper_runtime_decisions
            WHERE is_current_batch IS TRUE
            ORDER BY market_id, side
            """
        ).fetchall()

    decisions = {(row["market_id"], row["side"]): row for row in rows}
    assert result["unique_market_count"] == 3
    assert result["unique_market_side_count"] == 3
    assert decisions[("691547", "YES")]["decision"] in {"ENTER", "BLOCK"}
    assert decisions[("597967", "NO")]["decision"] == "WATCH"
    assert decisions[("597967", "NO")]["paper_enter_allowed"] is False
    assert "THESIS_WATCH_NOT_OBSERVATION_POLICY_ELIGIBLE" in decisions[("597967", "NO")]["warnings_json"]
    assert decisions[("666655", "YES")]["decision"] == "BLOCK"
    assert "THESIS_NOT_SUPPORTED" in decisions[("666655", "YES")]["blockers_json"]


def test_decision_service_groups_watch_rows_by_market_side(postgres_test_schema) -> None:
    _prepare()
    _seed_policy_review(
        review_id="review-watch-a",
        market_id="597967",
        side="NO",
        state="OBSERVATION_POLICY_WATCH",
        decision_band="HARD_BLOCKED",
        score=55.46,
        thesis_state="THESIS_WATCH",
        policy_blockers=["thesis_watch_not_observation_policy_eligible"],
        allowed=False,
    )
    _seed_policy_review(
        review_id="review-watch-b",
        market_id="597967",
        side="NO",
        state="OBSERVATION_POLICY_WATCH",
        decision_band="HARD_BLOCKED",
        score=54,
        thesis_state="THESIS_WATCH",
        policy_blockers=["thesis_watch_not_observation_policy_eligible"],
        allowed=False,
    )

    result = PaperRuntimeDecisionService().refresh(limit=10, force=True)

    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM paper_runtime_decisions WHERE is_current_batch IS TRUE").fetchone()["count"]

    assert count == 1
    assert result["duplicate_suppressed_count"] == 1


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


def _seed_policy_review(
    *,
    review_id: str,
    market_id: str,
    side: str,
    state: str,
    decision_band: str,
    score: float,
    thesis_state: str,
    policy_blockers: list[str],
    allowed: bool,
    exit_state: str = "EXIT_READY",
    orderbook_state: str = "FRESH",
    token_state: str = "TOKENS_VERIFIED",
) -> None:
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
            ON CONFLICT DO NOTHING
            """,
            (f"book-{review_id}", market_id, token_id, side, now, now, now),
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
                %s,%s,%s,
                'EDGE_SUPPORTED',%s,'RISK_OK','CAPITAL_WATCH',%s,
                'DATA_ONLY_RESEARCH',%s,%s,
                'CANDIDATE_SCOPED','COMPLETE',
                %s,true,true,false,false,false,false,5,
                1,3600,'[]'::jsonb,%s,%s,'[]'::jsonb,
                %s,'{}'::jsonb,'{}'::jsonb,'test policy review', %s
            )
            """,
            (
                review_id,
                f"seed-{review_id}",
                f"inq-{review_id}",
                f"payload-{review_id}",
                f"score-{review_id}",
                market_id,
                f"condition-{market_id}",
                side,
                token_id,
                state,
                decision_band,
                score,
                thesis_state,
                exit_state,
                orderbook_state,
                token_state,
                allowed,
                Jsonb(["capital_watch_not_full_paper_ready"]),
                Jsonb(policy_blockers),
                Jsonb({"source_event_id": f"event-{market_id}", "proactive_candidate_seed_id": f"seed-{review_id}"}),
                now,
            ),
        )


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])
