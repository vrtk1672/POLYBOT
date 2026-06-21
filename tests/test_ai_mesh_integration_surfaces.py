from __future__ import annotations

from psycopg.types.json import Jsonb

from app.control_center.system_overview import _ai_mesh_intelligence
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_ai_insights_appear_in_system_overview_snapshot(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM ai_mesh_insights")
        conn.execute(
            """
            INSERT INTO ai_mesh_insights (
                ai_mesh_insight_id, run_id, insight_type, market_id, side,
                proactive_candidate_seed_id, model_provider, model_name, prompt_version,
                summary, reasoning_brief, why_not_json, missing_evidence_json,
                recommended_mesh_action, is_execution_authority, metadata_json
            )
            VALUES (
                'ai-mesh-overview-1','run-overview','WHY_NOT','market-overview','YES',
                'seed-overview','OLLAMA','qwen3:4b','ai_full_mesh_intelligence_v1',
                'Missing hold time blocks entry.','advisory only',%s,%s,
                'BUILD_THESIS',false,%s
            )
            """,
            (
                Jsonb(["missing_dynamic_hold_time"]),
                Jsonb(["exit_or_time_stop"]),
                Jsonb({"execution_allowed": False, "paper_allowed": False}),
            ),
        )
        conn.execute(
            """
            INSERT INTO ai_mesh_intelligence_runs (
                run_id, status, started_at, completed_at, insights_created,
                calls_attempted, calls_succeeded, calls_failed, avg_latency_ms,
                local_model_status_json, metadata_json
            )
            VALUES ('run-overview','OK',now(),now(),1,1,1,0,12,%s,%s)
            """,
            (
                Jsonb({"available": True, "provider": "OLLAMA", "models": ["qwen3:4b"]}),
                Jsonb({"is_execution_authority": False}),
            ),
        )
        tables = _table_cache(conn)
        payload = _ai_mesh_intelligence(conn, tables)

    assert payload["status"] == "REAL"
    assert payload["total_insights"] == 1
    assert payload["local_model_status"]["provider"] == "OLLAMA"
    assert payload["top_why_not_reasons"] == ["missing_dynamic_hold_time: 1"]
    assert payload["candidates_kept_blocked_by_ai"] == 1


def test_system_overview_ai_surface_reports_missing_when_table_absent() -> None:
    assert _ai_mesh_intelligence(conn=_NoTableConn(), tables={})["status"] == "MISSING"


class _NoTableConn:
    pass


def _table_cache(conn) -> dict[str, set[str]]:
    rows = conn.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema=current_schema()
        """
    ).fetchall()
    cache: dict[str, set[str]] = {}
    for row in rows:
        cache.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    return cache
