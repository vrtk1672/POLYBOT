from __future__ import annotations

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.paper_observation_policy import PaperObservationPolicyReviewService


def test_policy_review_reads_non_paper_observation_mesh_rows_as_watch(postgres_test_schema) -> None:
    _prepare()
    _seed_mesh_row(
        market_id="597967",
        side="NO",
        result_id="result-watch",
        seed_id="seed-watch",
        inquiry_id="inq-watch",
        decision_band="HARD_BLOCKED",
        thesis_state="THESIS_WATCH",
        score=55.46,
        hard_blockers=["missing_dynamic_hold_time"],
        trigger_type="MARKET_MOVEMENT_TRIGGER",
    )

    result = PaperObservationPolicyReviewService().refresh(limit=20, force=True)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT market_id, side, observation_policy_state, observation_allowed_by_policy, policy_blockers_json
            FROM paper_observation_policy_reviews
            WHERE market_id='597967' AND side='NO'
            """
        ).fetchone()

    assert result["watch_count"] == 1
    assert row["observation_policy_state"] == "OBSERVATION_POLICY_WATCH"
    assert row["observation_allowed_by_policy"] is False
    assert "thesis_watch_not_observation_policy_eligible" in row["policy_blockers_json"]


def test_policy_review_keeps_thesis_missing_non_dominant_candidate_incomplete(postgres_test_schema) -> None:
    _prepare()
    _seed_mesh_row(
        market_id="666655",
        side="YES",
        result_id="result-missing",
        seed_id="seed-missing",
        inquiry_id="inq-missing",
        decision_band="HARD_BLOCKED",
        thesis_state="THESIS_MISSING",
        score=46.3,
        hard_blockers=["missing_trade_thesis", "exit_not_ready"],
        exit_state="EXIT_NOT_READY",
        trigger_type="PAYOUT_DISCREPANCY_TRIGGER",
    )

    result = PaperObservationPolicyReviewService().refresh(limit=20, force=True)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT observation_policy_state, policy_blockers_json
            FROM paper_observation_policy_reviews
            WHERE market_id='666655' AND side='YES'
            """
        ).fetchone()

    assert result["incomplete_count"] == 1
    assert row["observation_policy_state"] == "OBSERVATION_POLICY_INCOMPLETE"
    assert "thesis_not_supported" in row["policy_blockers_json"]


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_observation_policy_review_runs",
            "paper_observation_policy_reviews",
            "proactive_seed_mesh_results",
            "proactive_seed_mesh_inquiries",
            "proactive_candidate_seeds",
            "market_universe_memory",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _seed_mesh_row(
    *,
    market_id: str,
    side: str,
    result_id: str,
    seed_id: str,
    inquiry_id: str,
    decision_band: str,
    thesis_state: str,
    score: float,
    hard_blockers: list[str],
    trigger_type: str,
    exit_state: str = "EXIT_READY",
) -> None:
    now = datetime.now(UTC)
    token_id = f"{market_id}-{side.lower()}-token"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO market_universe_memory (
                market_memory_id, market_id, condition_id, question, status, active,
                token_verification_state, identity_verification_state, metadata_json
            )
            VALUES (%s,%s,%s,'test market','ACTIVE',true,'TOKENS_VERIFIED','VERIFIED','{}'::jsonb)
            """,
            (f"memory-{market_id}", market_id, f"condition-{market_id}"),
        )
        conn.execute(
            """
            INSERT INTO proactive_candidate_seeds (
                proactive_candidate_seed_id, seed_generation_run_id, source_event_id,
                targeted_revalidation_id, market_memory_id, market_id, condition_id,
                side, token_id, seed_state, seed_type, trigger_type, seed_generation_source,
                research_only, execution_allowed, paper_allowed, shadow_allowed, live_allowed,
                orderbook_refresh_state, token_side_resolution_state, candidate_event_scope_state,
                hard_blockers_json, soft_blockers_json, required_to_pass_json, metadata_json,
                created_at, updated_at
            )
            VALUES (
                %s,'run','event-1','reval-1',%s,%s,%s,%s,%s,'GENERATED','MULTI_TRIGGER',
                %s,'MULTI_TRIGGER',true,false,false,false,false,
                'FRESH','SIDE_DIRECTIONAL_' || %s,'CANDIDATE_SCOPED',
                '[]'::jsonb,'[]'::jsonb,'[]'::jsonb,'{}'::jsonb,%s,%s
            )
            """,
            (
                seed_id,
                f"memory-{market_id}",
                market_id,
                f"condition-{market_id}",
                side,
                token_id,
                trigger_type,
                side,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO proactive_seed_mesh_inquiries (
                seed_mesh_inquiry_id, proactive_candidate_seed_id, source_event_id,
                targeted_revalidation_id, market_memory_id, market_id, condition_id,
                side, token_id, request_state, research_only, execution_allowed,
                paper_allowed, shadow_allowed, live_allowed
            )
            VALUES (%s,%s,'event-1','reval-1',%s,%s,%s,%s,%s,'COMPLETED',true,false,false,false,false)
            """,
            (inquiry_id, seed_id, f"memory-{market_id}", market_id, f"condition-{market_id}", side, token_id),
        )
        conn.execute(
            """
            INSERT INTO proactive_seed_mesh_results (
                seed_mesh_result_id, seed_mesh_inquiry_id, proactive_candidate_seed_id,
                result_state, edge_state, trade_thesis_state, opportunity_score,
                opportunity_decision_band, risk_state, capital_state, exit_state,
                lifecycle_state, hard_blockers_json, soft_blockers_json,
                required_to_improve_json, metadata_json, created_at, updated_at
            )
            VALUES (
                %s,%s,%s,'MESH_DATA_ONLY_COMPLETED','EDGE_SUPPORTED',%s,%s,%s,
                'RISK_OK','CAPITAL_WATCH',%s,'DATA_ONLY_RESEARCH',%s,
                %s,'[]'::jsonb,'{}'::jsonb,%s,%s
            )
            """,
            (
                result_id,
                inquiry_id,
                seed_id,
                thesis_state,
                score,
                decision_band,
                exit_state,
                Jsonb(hard_blockers),
                Jsonb(["capital_watch_not_full_paper_ready"]),
                now,
                now,
            ),
        )


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])
