from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.ai_mesh_intelligence import (
    AIMarketIntelligenceMeshOrgan,
    build_candidate_context,
    build_candidate_insights,
    deterministic_candidate_insight,
)


class _FakeAI:
    def status(self) -> dict[str, object]:
        return {
            "available": True,
            "provider": "OLLAMA",
            "models": ["qwen3:4b"],
            "fast_model": "qwen3:4b",
            "reasoning_model": "qwen3:4b",
        }

    def complete_json(self, **kwargs) -> dict[str, object]:
        return {
            "_model_provider": "OLLAMA",
            "_model_name": "qwen3:4b",
            "summary": "Movement evidence supports a watchable momentum thesis.",
            "reasoning_brief": "Uses only supplied trigger and Mesh states.",
            "direction_hint": "YES",
            "direction_confidence": 0.62,
            "thesis_type": "MOMENTUM_CONTINUATION",
            "thesis_confidence": 0.64,
            "expected_hold_time_seconds": 14400,
            "time_stop_seconds": 14400,
            "invalidation_condition": "Invalidate if movement reverses or orderbook support fades.",
            "missing_evidence": ["independent_confirmation"],
            "why_not": ["THESIS_WATCH"],
            "recommended_mesh_action": "BUILD_THESIS",
            "confidence": 0.64,
        }


def test_ai_insight_records_are_non_execution_authority() -> None:
    context = build_candidate_context(
        {
            "market_id": "m1",
            "side": "YES",
            "token_id": "t1",
            "proactive_candidate_seed_id": "seed1",
            "seed_mesh_inquiry_id": "inq1",
            "trigger_type": "MARKET_MOVEMENT_TRIGGER",
            "thesis_state": "THESIS_WATCH",
            "exit_state": "EXIT_NOT_READY",
            "policy_blockers_json": ["thesis_watch_not_observation_policy_eligible"],
        }
    )
    ai = deterministic_candidate_insight(context, ai_unavailable=False)
    insights = build_candidate_insights(context, ai, run_id="run1")

    assert insights
    assert all(item["is_execution_authority"] is False for item in insights)
    assert all(item["metadata_json"]["execution_allowed"] is False for item in insights)
    assert {item["insight_type"] for item in insights} >= {"TRADE_THESIS", "WHY_NOT", "EXIT_PLAN"}


def test_ai_mesh_refresh_persists_records_without_trading_artifacts(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM ai_mesh_insights")
        conn.execute("DELETE FROM paper_observation_policy_reviews")
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
                'review-ai-1','PROACTIVE_SEED_MESH','seed-ai-1','inq-ai-1',
                'market-ai-1','condition-ai-1','YES','token-ai-1',
                'OBSERVATION_POLICY_WATCH','PAPER_OBSERVATION',61,
                'EDGE_SUPPORTED','THESIS_WATCH','RISK_REVIEW','CAPITAL_WATCH',
                'EXIT_NOT_READY','DATA_ONLY_RESEARCH','FRESH','TOKENS_VERIFIED',
                'CANDIDATE_SCOPED','COMPLETE',false,true,true,false,false,false,false,
                5,1,86400,'[]'::jsonb,'[]'::jsonb,%s,%s,%s,'{}'::jsonb,'{}'::jsonb,'watch'
            )
            """,
            (
                Jsonb(["thesis_watch_not_observation_policy_eligible", "exit_not_ready"]),
                Jsonb(["Trade thesis must move from watch to supported.", "Exit must be ready."]),
                Jsonb({"proactive_candidate_seed_id": "seed-ai-1", "seed_mesh_inquiry_id": "inq-ai-1"}),
            ),
        )
        before_intents = _count(conn, "paper_intents")

    result = AIMarketIntelligenceMeshOrgan(local_ai=_FakeAI()).refresh(limit=1, force=True)

    with DatabaseConnectionFactory().connect() as conn:
        after_intents = _count(conn, "paper_intents")
        insight_count = _count(conn, "ai_mesh_insights")
        authority = conn.execute("SELECT bool_or(is_execution_authority) AS value FROM ai_mesh_insights").fetchone()["value"]

    assert result["insights_created"] >= 1
    assert insight_count >= 1
    assert authority is False
    assert before_intents == after_intents


def _count(conn, table: str) -> int:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    if not row or not row["table_name"]:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
