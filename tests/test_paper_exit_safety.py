from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from test_paper_exit_loop import _lock_position, _prepare, _seed_position, _service


def test_paper_exit_loop_does_not_create_orders_fills_or_positions(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55)
    _lock_position(position_id)
    with DatabaseConnectionFactory().connect() as conn:
        before = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "paper_positions": conn.execute("SELECT COUNT(*) AS count FROM paper_positions").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "fills": conn.execute("SELECT COUNT(*) AS count FROM fills_v2").fetchone()["count"],
            "positions": conn.execute("SELECT COUNT(*) AS count FROM positions").fetchone()["count"],
        }

    result = _service().run_exit_loop(correlation_id="safety")

    with DatabaseConnectionFactory().connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "paper_positions": conn.execute("SELECT COUNT(*) AS count FROM paper_positions").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "fills": conn.execute("SELECT COUNT(*) AS count FROM fills_v2").fetchone()["count"],
            "positions": conn.execute("SELECT COUNT(*) AS count FROM positions").fetchone()["count"],
        }

    assert result["closed_positions_count"] == 1
    assert after == before
    assert result["live_orders_delta"] == 0
    assert result["real_orders_delta"] == 0
    assert result["fills_delta"] == 0
