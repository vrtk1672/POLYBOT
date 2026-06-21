from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.brain_outputs import BrainOutput
from app.services.brain_outputs import BrainOutputService
from app.services.dry_run_provenance import DryRunProvenanceService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM dry_run_provenance_runs")
        conn.execute("DELETE FROM dry_run_provenance_analysis")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
    BrainOutputService().create_brain_output(
        BrainOutput(
            brain_output_id="safety-provenance-bo",
            brain="risk",
            output_type="RISK_WARNING",
            recommendation="NO_TRADE_HINT",
            status="ACTIVE",
            generated_by="mesh_dry_run",
            metadata={"dry_run_phase": "v2_part4b"},
        )
    )


def test_dry_run_provenance_does_not_create_orders_or_enable_paper(postgres_test_schema) -> None:
    _prepare()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = _safety_counts(conn)

    result = DryRunProvenanceService().analyze_recent(limit=10)

    with factory.connect() as conn:
        after = _safety_counts(conn)
    assert result["summary"]["brain_outputs_dry_run"] == 1
    assert result["summary"]["can_feed_paper_by_provenance_count"] == 0
    assert after == before


def _safety_counts(conn) -> dict[str, int]:
    return {
        "paper_orders": int(conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"]),
        "shadow_orders": int(conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"]),
        "live_orders": int(conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"]),
        "order_intents": _table_count(conn, "order_intents"),
        "execution_allowed": int(conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed IS TRUE").fetchone()["count"]),
    }


def _table_count(conn, table_name: str) -> int:
    exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table_name,)).fetchone()["table_name"]
    if not exists:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"])
