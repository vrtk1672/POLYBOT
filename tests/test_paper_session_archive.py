from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_session import PaperSessionService
from paper_session_helpers import OLD_POSITION_ID, prepare_paper_session_fixture


def test_reset_preserves_old_rows_and_archives_previous_session(postgres_test_schema) -> None:
    prepare_paper_session_fixture()

    result = PaperSessionService().reset(balance=1000, reason="archive test", created_by="test")

    with DatabaseConnectionFactory().connect() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions")
        }
        previous = conn.execute("SELECT * FROM paper_sessions WHERE paper_session_id=%s", (result["previous_session_id"],)).fetchone()
        position = conn.execute("SELECT * FROM paper_positions WHERE id=%s", (OLD_POSITION_ID,)).fetchone()
        close = conn.execute("SELECT * FROM paper_position_closes WHERE position_id=%s", (OLD_POSITION_ID,)).fetchone()
    assert counts == {"paper_intents": 1, "paper_orders": 1, "paper_fills": 1, "paper_positions": 1}
    assert previous["status"] == "RESET_CLOSED"
    assert position["current_status"] == "RESET_CLOSED"
    assert position["closed_at"] is not None
    assert position["excluded_from_active_paper_truth"] is True
    assert close["exit_reason"] == "RESET_CLOSED"
