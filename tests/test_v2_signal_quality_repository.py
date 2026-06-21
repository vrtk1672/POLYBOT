from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.neural_mesh.lineage import SignalLineage
from app.neural_mesh.signal_quality import SignalQualityEvaluation
from app.repositories.signal_lineage_repository import SignalLineageRepository
from app.repositories.signal_quality_repository import SignalQualityRepository
from app.services.neuron_signals import NeuronSignalService
from app.services.signal_quality import SignalQualityService


def _prepare() -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_quality_evaluations")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signals")


def _signal() -> dict[str, object]:
    return NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            status="ACTIVE",
            market_id="quality-market",
            raw_direction="neutral",
            confidence=0.9,
            strength=0.8,
            freshness_seconds=0,
            evidence={"resolution_status": "clear"},
            raw_payload_ref="rules:quality",
            stale_after_seconds=3600,
        )
    )


def _bind_and_link(signal_id: str) -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        SignalLineageRepository().attach_signal_binding(
            conn,
            SignalLineage(
                signal_id=signal_id,
                neuron_name="rules",
                producer_name="rules_resolution_adapter",
                source_name="rules_resolution_truth",
                market_id="quality-market",
                correlation_id="quality-correlation",
                raw_payload_ref="rules:quality",
                generated_from="rules_resolution",
            ),
        )
        conn.execute(
            """
            INSERT INTO signal_market_links (signal_id, market_id, link_type, link_status, confidence, reason, created_by)
            VALUES (%s, 'quality-market', 'exact_match', 'confirmed', 1.0, 'test link', 'quality_test')
            """,
            (signal_id,),
        )


def test_upsert_signal_quality_evaluation_persists_missing_fields_and_reason(postgres_test_schema) -> None:
    _prepare()
    signal = _signal()
    evaluation = SignalQualityEvaluation(
        signal_id=str(signal["signal_id"]),
        quality_score=0.42,
        quality_status="WEAK",
        missing_fields=["lineage", "market_link"],
        readiness_reason="missing lineage and market link",
    )
    repo = SignalQualityRepository()

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        row = repo.upsert_evaluation(conn, evaluation)
        loaded = repo.get_evaluation(conn, str(signal["signal_id"]))

    assert row["signal_id"] == signal["signal_id"]
    assert loaded is not None
    assert loaded["missing_fields_json"] == ["lineage", "market_link"]
    assert loaded["readiness_reason"] == "missing lineage and market link"


def test_service_evaluates_and_persists_quality_from_existing_truth(postgres_test_schema) -> None:
    _prepare()
    signal = _signal()
    _bind_and_link(str(signal["signal_id"]))

    result = SignalQualityService().evaluate_signal_quality(str(signal["signal_id"]))

    assert result is not None
    assert result["has_lineage"] is True
    assert result["linked_to_market"] is True
    assert result["can_feed_brain"] is True
    assert result["quality_score"] >= 0.8


def test_summary_reports_distribution_and_missing_fields(postgres_test_schema) -> None:
    _prepare()
    signal = _signal()

    SignalQualityService().evaluate_signal_quality(str(signal["signal_id"]))
    summary = SignalQualityService().get_signal_quality_summary()

    assert summary["mock_data"] is False
    assert summary["total_evaluated"] == 1
    assert summary["quality_by_status"]
    assert summary["missing_fields_summary"]
