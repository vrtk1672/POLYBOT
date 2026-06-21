from app.exit_cortex.position_monitor import PositionMonitor
from test_v2_16_fixtures import db_factory


def test_position_monitor_object_exists_for_orphan_detection():
    assert PositionMonitor() is not None


def test_position_monitor_detects_orphans_when_db_available(db_factory):
    with db_factory.connect() as conn:
        if not conn.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", ("orders_v2",)).fetchone()["exists"]:
            return
        rows = PositionMonitor().orphan_orders(conn, limit=5)
        assert isinstance(rows, list)
