from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.brain_outputs import BrainOutput, BrainOutputDependency
from app.services.brain_coordinator import BrainCoordinatorService
from app.services.brain_outputs import BrainOutputService
from app.services.dry_run_provenance import DryRunProvenanceService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM dry_run_provenance_runs")
        conn.execute("DELETE FROM dry_run_provenance_analysis")
        conn.execute("DELETE FROM mesh_dry_run_items")
        conn.execute("DELETE FROM mesh_dry_runs")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
        conn.execute("DELETE FROM neuron_signals")


def _brain_output(*, brain_output_id: str, generated_by: str) -> dict[str, object]:
    return BrainOutputService().create_brain_output(
        BrainOutput(
            brain_output_id=brain_output_id,
            brain="risk",
            output_type="RISK_WARNING",
            recommendation="NO_TRADE_HINT",
            status="ACTIVE",
            generated_by=generated_by,
            metadata={"dry_run_phase": "v2_part4b"} if generated_by == "mesh_dry_run" else {},
        )
    )


def test_repository_separates_brain_output_runtime_vs_dry_run(postgres_test_schema) -> None:
    _prepare()
    _brain_output(brain_output_id="bo-dry", generated_by="mesh_dry_run")
    _brain_output(brain_output_id="bo-runtime", generated_by="runtime")

    result = DryRunProvenanceService().analyze_recent(limit=10)

    assert result["mock_data"] is False
    assert result["summary"]["brain_outputs_total"] == 2
    assert result["summary"]["brain_outputs_dry_run"] == 1
    assert result["summary"]["brain_outputs_runtime"] == 1


def test_coordinator_decision_inherits_dry_run_from_inputs(postgres_test_schema) -> None:
    _prepare()
    output = _brain_output(brain_output_id="bo-dry-input", generated_by="mesh_dry_run")
    decision = BrainCoordinatorService().coordinate_outputs([str(output["brain_output_id"])])

    result = DryRunProvenanceService().analyze_recent(limit=10)

    assert result["summary"]["coordinator_decisions_total"] == 1
    assert result["summary"]["coordinator_decisions_dry_run"] == 1
    item = DryRunProvenanceService().get_provenance("COORDINATOR_DECISION", str(decision["coordinator_decision_id"]))
    assert item is not None
    assert item["provenance_status"] == "DRY_RUN_ONLY"


def test_provenance_upsert_is_idempotent(postgres_test_schema) -> None:
    _prepare()
    _brain_output(brain_output_id="bo-idempotent", generated_by="mesh_dry_run")

    DryRunProvenanceService().analyze_recent(limit=10)
    DryRunProvenanceService().analyze_recent(limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM dry_run_provenance_analysis").fetchone()["count"]
    assert count == 1
