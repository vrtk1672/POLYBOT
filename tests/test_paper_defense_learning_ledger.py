from __future__ import annotations

from decimal import Decimal

from psycopg.types.json import Jsonb
import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.config import get_database_settings
from app.db.migrate import run_migrations
from app.services.paper_defense import record_learning_decision


def test_learning_ledger_records_ignored_and_softened_blockers(postgres_test_schema) -> None:
    if not get_database_settings().database_url:
        pytest.skip("POLYBOT_DATABASE_URL is not configured")
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM paper_learning_ledger WHERE runtime_decision_id='decision-defense-ledger-test'")
        conn.execute("DELETE FROM paper_sessions WHERE paper_session_id='paper-defense-ledger-session'")
        conn.execute(
            """
            INSERT INTO paper_sessions (
                paper_session_id, session_name, starting_balance,
                current_balance_snapshot, realized_pnl, unrealized_pnl,
                net_pnl, status, started_at, created_by, metadata_json, defense_level
            )
            VALUES ('paper-defense-ledger-session','Defense Ledger',1000,1000,0,0,0,'ACTIVE',now(),'test','{}'::jsonb,20)
            """
        )
        record_learning_decision(
            conn,
            {
                "decision_id": "decision-defense-ledger-test",
                "market_id": "market-defense",
                "side": "YES",
                "opportunity_score": Decimal("55.46"),
                "blockers_json": [],
                "evidence": {
                    "paper_defense": {
                        "defense_level": 20,
                        "base_threshold": 60,
                        "adjusted_threshold": 42,
                        "strict_verdict": "BLOCKED",
                        "effective_verdict": "ALLOWED_FOR_LEARNING",
                        "strict_blockers": ["THESIS_NOT_SUPPORTED"],
                        "effective_blockers": [],
                        "ignored_blockers": ["THESIS_NOT_SUPPORTED"],
                        "softened_blockers": [],
                        "fallback_requirements": [],
                        "exit_plan_type": "FULL",
                    }
                },
            },
        )
        row = conn.execute(
            "SELECT ignored_blockers_json FROM paper_learning_ledger WHERE runtime_decision_id='decision-defense-ledger-test'"
        ).fetchone()
    assert row is not None
    assert row["ignored_blockers_json"] == ["THESIS_NOT_SUPPORTED"] or row["ignored_blockers_json"] == Jsonb(["THESIS_NOT_SUPPORTED"])
