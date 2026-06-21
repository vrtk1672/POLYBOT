from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.config import get_database_settings
from app.db.migrate import run_migrations
from app.services.paper_defense import PaperDefenseGovernor
import pytest


def test_session_learning_report_has_stable_sections() -> None:
    if not get_database_settings().database_url:
        pytest.skip("POLYBOT_DATABASE_URL is not configured")
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("UPDATE paper_sessions SET status='ARCHIVED', closed_at=COALESCE(closed_at, now()) WHERE status='ACTIVE'")
        conn.execute("DELETE FROM paper_sessions WHERE paper_session_id='paper-defense-report-session'")
        conn.execute(
            """
            INSERT INTO paper_sessions (
                paper_session_id, session_name, starting_balance,
                current_balance_snapshot, realized_pnl, unrealized_pnl,
                net_pnl, status, started_at, created_by, metadata_json, defense_level
            )
            VALUES ('paper-defense-report-session','Defense Report',1000,1000,0,0,0,'ACTIVE',now(),'test','{}'::jsonb,20)
            """
        )
    report = PaperDefenseGovernor().learning_report(session_id="paper-defense-report-session", write_files=False)
    assert report["schema_version"] == "paper_session_learning_report_v1"
    assert "session_metadata" in report
    assert "result_summary" in report
    assert "hunting_summary" in report
    assert "trade_table" in report
    assert "machine_learning_export" in report
