from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.neural_mesh.lineage import SignalLineage
from app.repositories.signal_lineage_repository import SignalLineageRepository
from app.services.lineage_coverage import LineageCoverageService
from app.services.neuron_signals import NeuronSignalService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_lineage_coverage_runs")
        conn.execute("DELETE FROM signal_lineage_coverage_analysis")
        conn.execute("DELETE FROM signal_link_coverage_runs")
        conn.execute("DELETE FROM signal_suggested_market_links")
        conn.execute("DELETE FROM signal_link_coverage_analysis")
        conn.execute("DELETE FROM signal_processing_state_history")
        conn.execute("DELETE FROM signal_processing_states")
        conn.execute("DELETE FROM signal_quality_evaluations")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")


def _signal(signal_id: str, *, source_name: str | None = "rules_resolution_truth", raw_payload_ref: str | None = "rules:test") -> dict[str, object]:
    return NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id=signal_id,
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name=source_name,
            status="ACTIVE",
            confidence=0.8,
            strength=0.8,
            evidence={"resolution_status": "clear"},
            raw_payload_ref=raw_payload_ref,
            correlation_id=f"corr-{signal_id}",
        )
    )


def _bind(signal_id: str, *, producer_name: str = "rules_resolution_adapter", raw_payload_ref: str | None = "rules:test") -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        SignalLineageRepository().attach_signal_binding(
            conn,
            SignalLineage(
                signal_id=signal_id,
                neuron_name="rules",
                producer_name=producer_name,
                source_name="rules_resolution_truth",
                source_event_id=f"event-{signal_id}",
                correlation_id=f"corr-{signal_id}",
                raw_payload_ref=raw_payload_ref,
                generated_from="rules_resolution",
                lineage={"raw_payload_policy": "reference_only"},
            ),
        )


def test_repository_upsert_is_idempotent(postgres_test_schema) -> None:
    _prepare()
    signal = _signal("lineage-idempotent")
    _bind(str(signal["signal_id"]))

    service = LineageCoverageService()
    first = service.analyze_signal(str(signal["signal_id"]))
    second = service.analyze_signal(str(signal["signal_id"]))

    assert first is not None
    assert second is not None
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM signal_lineage_coverage_analysis").fetchone()["count"]
    assert count == 1


def test_run_summary_counts_bound_and_unbound(postgres_test_schema) -> None:
    _prepare()
    bound = _signal("lineage-bound")
    _bind(str(bound["signal_id"]))
    _signal("lineage-unbound", source_name=None)

    result = LineageCoverageService().analyze_recent_signals(limit=10)

    assert result["mock_data"] is False
    assert result["analyzed"] == 2
    assert result["summary"]["total_analyzed"] == 2
    assert result["summary"]["bound_signals"] >= 1
    assert result["summary"]["unbound_signals"] >= 1
    with DatabaseConnectionFactory().connect() as conn:
        runs = conn.execute("SELECT COUNT(*) AS count FROM signal_lineage_coverage_runs").fetchone()["count"]
    assert runs == 1


def test_missing_raw_payload_is_persisted(postgres_test_schema) -> None:
    _prepare()
    signal = _signal("lineage-missing-raw", raw_payload_ref=None)
    _bind(str(signal["signal_id"]), raw_payload_ref=None)

    result = LineageCoverageService().analyze_signal(str(signal["signal_id"]))

    assert result is not None
    assert "MISSING_RAW_PAYLOAD_REF" in result["missing_lineage_fields"]
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT missing_lineage_fields_json FROM signal_lineage_coverage_analysis WHERE signal_id = %s", (signal["signal_id"],)).fetchone()
    assert "MISSING_RAW_PAYLOAD_REF" in row["missing_lineage_fields_json"]
