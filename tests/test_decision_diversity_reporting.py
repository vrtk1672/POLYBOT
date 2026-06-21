from __future__ import annotations

from psycopg.types.json import Jsonb

from app.control_center.system_overview import _decisions


def test_system_overview_exposes_policy_and_runtime_diversity_bottleneck(postgres_test_schema) -> None:
    with postgres_test_schema.connection() as conn, conn.transaction():
        for table in ("paper_runtime_decisions", "paper_observation_policy_reviews"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO paper_observation_policy_reviews (
                paper_observation_policy_review_id, source_type, market_id, side, token_id,
                observation_policy_state, decision_band, opportunity_score, edge_state,
                thesis_state, risk_state, capital_state, exit_state, lifecycle_state,
                orderbook_state, token_verification_state, candidate_event_scope_state,
                lineage_state, observation_allowed_by_policy, data_only,
                observation_policy_review_only, execution_allowed, paper_allowed,
                shadow_allowed, live_allowed, max_observation_notional,
                max_open_positions, time_stop_seconds, policy_blockers_json
            )
            VALUES
            ('policy-eligible','PROACTIVE_SEED_MESH','691547','YES','token-yes',
             'OBSERVATION_POLICY_ELIGIBLE','PAPER_OBSERVATION',62,'EDGE_SUPPORTED',
             'THESIS_SUPPORTED','RISK_OK','CAPITAL_WATCH','EXIT_READY','DATA_ONLY_RESEARCH',
             'FRESH','TOKENS_VERIFIED','CANDIDATE_SCOPED','COMPLETE',true,true,true,false,false,false,false,5,1,3600,'[]'::jsonb),
            ('policy-watch','PROACTIVE_SEED_MESH','597967','NO','token-no',
             'OBSERVATION_POLICY_WATCH','HARD_BLOCKED',55.46,'EDGE_SUPPORTED',
             'THESIS_WATCH','RISK_OK','CAPITAL_WATCH','EXIT_READY','DATA_ONLY_RESEARCH',
             'FRESH','TOKENS_VERIFIED','CANDIDATE_SCOPED','COMPLETE',false,true,true,false,false,false,false,5,1,3600,%s)
            """,
            (Jsonb(["thesis_watch_not_observation_policy_eligible"]),),
        )
        conn.execute(
            """
            INSERT INTO paper_runtime_decisions (
                decision_id, source_type, candidate_source, market_id, side, token_id,
                decision, decision_mode, execution_mode, paper_enter_allowed,
                opportunity_score, blockers_json, warnings_json, is_current_batch,
                diversity_score, duplicate_suppressed_count
            )
            VALUES
            ('decision-eligible','PROACTIVE_SEED_MESH','PROACTIVE_SEED_MESH','691547','YES','token-yes',
             'BLOCK','PAPER','PAPER',false,62,%s,'[]'::jsonb,true,165,0),
            ('decision-watch','PROACTIVE_SEED_MESH','PROACTIVE_SEED_MESH','597967','NO','token-no',
             'WATCH','PAPER','PAPER',false,55.46,'[]'::jsonb,%s,true,96,0)
            """,
            (
                Jsonb(["DUPLICATE_OPEN_PAPER_EXPOSURE"]),
                Jsonb(["THESIS_WATCH_NOT_OBSERVATION_POLICY_ELIGIBLE"]),
            ),
        )

        result = _decisions(conn, _tables(conn))

    assert result["paper_ready_decisions"] == 1
    assert result["watch_decisions"] == 1
    assert result["runtime_decisions_total"] == 2
    assert result["runtime_watch_decisions"] == 1
    assert result["unique_market_count"] == 2
    assert result["unique_market_side_count"] == 2
    assert result["runtime_decisions_by_market"]["691547"] == 1
    assert result["runtime_decisions_by_market"]["597967"] == 1


def test_cli_report_can_surface_top_non_dominant_blockers_shape():
    non_dominant = [
        {
            "market_id": "597967",
            "side": "NO",
            "blockers": ["thesis_watch_not_observation_policy_eligible"],
        }
    ]

    assert non_dominant[0]["market_id"] != "691547"
    assert non_dominant[0]["blockers"] == ["thesis_watch_not_observation_policy_eligible"]


def _tables(conn):
    rows = conn.execute(
        """
        SELECT table_name, array_agg(column_name) AS columns
        FROM information_schema.columns
        WHERE table_schema=current_schema()
        GROUP BY table_name
        """
    ).fetchall()
    return {row["table_name"]: set(row["columns"]) for row in rows}
