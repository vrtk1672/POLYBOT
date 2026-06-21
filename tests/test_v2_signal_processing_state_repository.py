from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.brain_outputs import BrainOutput, BrainOutputDependency
from app.neural_mesh.contracts import NeuronSignal
from app.neural_mesh.coordinator import CoordinatorDecision, CoordinatorDecisionInput
from app.neural_mesh.signal_quality import SignalQualityEvaluation
from app.repositories.brain_output_repository import BrainOutputRepository
from app.repositories.coordinator_repository import CoordinatorRepository
from app.repositories.signal_quality_repository import SignalQualityRepository
from app.services.neuron_signals import NeuronSignalService
from app.services.signal_processing import SignalProcessingService


def _prepare() -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_processing_state_history")
        conn.execute("DELETE FROM signal_processing_states")
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


def _signal(*, signal_id: str = "processing-signal", market_id: str | None = "processing-market") -> dict[str, object]:
    return NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id=signal_id,
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            status="ACTIVE",
            market_id=market_id,
            raw_direction="neutral",
            confidence=0.8,
            strength=0.7,
            evidence={"resolution_status": "clear"},
        )
    )


def _quality(signal_id: str, **overrides) -> None:
    base = {
        "signal_id": signal_id,
        "quality_score": 0.62,
        "quality_status": "PARTIAL",
        "missing_fields": ["linked_to_position"],
        "readiness_reason": "usable for brain only",
        "can_feed_brain": True,
        "can_feed_paper": False,
        "has_market_id": True,
        "has_source": True,
        "has_lineage": True,
        "has_correlation_id": True,
        "has_raw_payload_ref": True,
        "has_confidence": True,
        "has_strength": True,
        "has_freshness": True,
        "has_evidence": True,
        "linked_to_market": True,
        "linked_to_position": False,
        "is_runtime_generated": True,
    }
    base.update(overrides)
    evaluation = SignalQualityEvaluation(**base)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        SignalQualityRepository().upsert_evaluation(conn, evaluation)


def _brain_used(signal_id: str) -> str:
    brain_output_id = "brain-processing"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        repo = BrainOutputRepository()
        repo.create_brain_output(
            conn,
            BrainOutput(
                brain_output_id=brain_output_id,
                brain="context",
                output_type="WATCH",
                market_id="processing-market",
                recommendation="WATCH",
                confidence=0.6,
                reasoning_summary="test output",
                status="ACTIVE",
            ),
        )
        repo.add_dependency(
            conn,
            BrainOutputDependency(
                brain_output_id=brain_output_id,
                dependency_type="signal",
                dependency_id=signal_id,
            ),
        )
    return brain_output_id


def _coordinator_used(brain_output_id: str) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        repo = CoordinatorRepository()
        repo.create_decision(
            conn,
            CoordinatorDecision(
                coordinator_decision_id="coord-processing",
                market_id="processing-market",
                final_state="WATCH",
                primary_reason="test non-executing coordination",
                approved_actions=["WATCH"],
                blocked_actions=["EXECUTION"],
                source_brain_count=1,
                input_output_count=1,
            ),
        )
        repo.add_input(
            conn,
            CoordinatorDecisionInput(
                coordinator_decision_id="coord-processing",
                brain_output_id=brain_output_id,
                brain="context",
                input_recommendation="WATCH",
            ),
        )


def test_repository_upsert_is_idempotent_and_records_first_transition(postgres_test_schema) -> None:
    _prepare()
    signal = _signal()
    _quality(str(signal["signal_id"]))
    service = SignalProcessingService()

    first = service.evaluate_signal_processing(str(signal["signal_id"]))
    second = service.evaluate_signal_processing(str(signal["signal_id"]))

    assert first is not None
    assert second is not None
    assert first["processing_state"] == "QUALITY_CHECKED"
    with DatabaseConnectionFactory().connect() as conn:
        states = conn.execute("SELECT COUNT(*) AS count FROM signal_processing_states").fetchone()["count"]
        history = conn.execute("SELECT COUNT(*) AS count FROM signal_processing_state_history").fetchone()["count"]
    assert states == 1
    assert history == 1


def test_brain_and_coordinator_usage_upgrade_processing_state(postgres_test_schema) -> None:
    _prepare()
    signal = _signal()
    _quality(str(signal["signal_id"]))
    brain_output_id = _brain_used(str(signal["signal_id"]))
    brain_state = SignalProcessingService().evaluate_signal_processing(str(signal["signal_id"]))

    assert brain_state is not None
    assert brain_state["processing_state"] == "BRAIN_USED"

    _coordinator_used(brain_output_id)
    coordinator_state = SignalProcessingService().evaluate_signal_processing(str(signal["signal_id"]))

    assert coordinator_state is not None
    assert coordinator_state["processing_state"] == "COORDINATOR_USED"
    assert coordinator_state["used_by_coordinator"] is True


def test_mark_ignored_and_error_require_reasons_at_service_boundary(postgres_test_schema) -> None:
    _prepare()
    signal = _signal()
    service = SignalProcessingService()
    try:
        service.mark_ignored(str(signal["signal_id"]), ignored_reason="")
    except ValueError as exc:
        assert "ignored_reason" in str(exc)
    else:
        raise AssertionError("mark_ignored accepted an empty reason")

    try:
        service.mark_error(str(signal["signal_id"]), error_reason="")
    except ValueError as exc:
        assert "error_reason" in str(exc)
    else:
        raise AssertionError("mark_error accepted an empty reason")
