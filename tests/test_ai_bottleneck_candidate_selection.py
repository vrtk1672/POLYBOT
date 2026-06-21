from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.ai_mesh_intelligence import _candidate_context_rows
from psycopg.types.json import Jsonb


def test_non_dominant_thesis_missing_candidates_are_prioritized(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM ai_mesh_insights")
        conn.execute("DELETE FROM paper_observation_policy_reviews")
        for idx in range(4):
            _insert_review(conn, f"review-dom-{idx}", f"seed-dom-{idx}", "m-dominant", "YES")
        _insert_review(conn, "review-non-dom", "seed-non-dom", "m-non-dominant", "NO")

        rows = _candidate_context_rows(conn, limit=2, force=True)

    assert any(row["market_id"] == "m-non-dominant" for row in rows)
    assert not all(row["market_id"] == "m-dominant" for row in rows)


def _insert_review(conn, review_id: str, seed_id: str, market_id: str, side: str) -> None:
    conn.execute(
        """
        INSERT INTO paper_observation_policy_reviews (
            paper_observation_policy_review_id, source_type, proactive_candidate_seed_id,
            seed_mesh_inquiry_id, market_id, condition_id, side, token_id,
            observation_policy_state, decision_band, opportunity_score,
            edge_state, thesis_state, risk_state, capital_state, exit_state,
            lifecycle_state, orderbook_state, token_verification_state,
            candidate_event_scope_state, lineage_state,
            observation_allowed_by_policy, data_only, observation_policy_review_only,
            execution_allowed, paper_allowed, shadow_allowed, live_allowed,
            max_observation_notional, max_open_positions, time_stop_seconds,
            hard_blockers_json, soft_blockers_json, policy_blockers_json,
            required_to_pass_json, lineage_json, limits_json, metadata_json, policy_reason
        )
        VALUES (
            %s,'PROACTIVE_SEED_MESH',%s,%s,
            %s,%s,%s,%s,
            'OBSERVATION_POLICY_INCOMPLETE','HARD_BLOCKED',46,
            'EDGE_SUPPORTED','THESIS_MISSING','RISK_OK','CAPITAL_WATCH',
            'EXIT_NOT_READY','DATA_ONLY_RESEARCH','FRESH','TOKENS_VERIFIED',
            'CANDIDATE_SCOPED','COMPLETE',false,true,true,false,false,false,false,
            5,1,86400,'[]'::jsonb,'[]'::jsonb,%s,%s,%s,'{}'::jsonb,'{}'::jsonb,'incomplete'
        )
        """,
        (
            review_id,
            seed_id,
            f"inq-{seed_id}",
            market_id,
            f"condition-{market_id}",
            side,
            f"token-{market_id}-{side}",
            Jsonb(["missing_trade_thesis", "exit_not_ready"]),
            Jsonb(["Build thesis", "Define exit"]),
            Jsonb({"proactive_candidate_seed_id": seed_id}),
        ),
    )
