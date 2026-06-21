from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.neural_mesh.signal_quality import SignalQualityEvaluation
from app.repositories.signal_quality_repository import SignalQualityRepository
from app.services.neuron_signals import NeuronSignalService
from app.services.signal_processing import SignalProcessingService


def _prepare() -> dict[str, object]:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_processing_state_history")
        conn.execute("DELETE FROM signal_processing_states")
        conn.execute("DELETE FROM signal_quality_evaluations")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
    return NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            status="ACTIVE",
            market_id="gate-market",
            confidence=0.9,
            strength=0.9,
            evidence={"resolution_status": "clear"},
            raw_payload_ref="rules:gate",
            freshness_seconds=0,
            stale_after_seconds=3600,
        )
    )


def _quality(signal_id: str, **overrides) -> None:
    base = {
        "signal_id": signal_id,
        "quality_score": 0.92,
        "quality_status": "GOOD",
        "missing_fields": [],
        "readiness_reason": "full metadata",
        "can_feed_brain": True,
        "can_feed_paper": True,
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
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        SignalQualityRepository().upsert_evaluation(conn, SignalQualityEvaluation(**base))


def test_can_feed_paper_stays_signal_level_informational_only(postgres_test_schema) -> None:
    signal = _prepare()
    _quality(str(signal["signal_id"]))

    result = SignalProcessingService().evaluate_signal_processing(str(signal["signal_id"]))
    summary = SignalProcessingService().get_signal_processing_summary()

    assert result is not None
    assert result["gate_status"] == "PAPER_ELIGIBLE_INFORMATIONAL_ONLY"
    assert result["can_feed_paper"] is True
    assert summary["paper_eligible_informational_count"] == 1
    assert summary["paper_ready"] is False


def test_dry_run_generated_quality_is_blocked_from_paper_evidence(postgres_test_schema) -> None:
    signal = _prepare()
    _quality(
        str(signal["signal_id"]),
        quality_score=0.68,
        quality_status="DRY_RUN_ONLY",
        missing_fields=["production_market_link"],
        readiness_reason="dry-run evidence is informational only",
        can_feed_paper=False,
        is_dry_run_generated=True,
        is_runtime_generated=False,
    )

    result = SignalProcessingService().evaluate_signal_processing(str(signal["signal_id"]))

    assert result is not None
    assert result["can_feed_paper"] is False
    assert result["gate_status"] == "BRAIN_ELIGIBLE"
    assert "dry_run_generated" in result["blocked_by"]
    assert "production_market_link" in result["missing_requirements"]


def test_no_order_intents_or_orders_are_created_by_gate_evaluation(postgres_test_schema) -> None:
    signal = _prepare()
    _quality(str(signal["signal_id"]))
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "order_intents": _table_count(conn, "order_intents"),
        }

    SignalProcessingService().evaluate_signal_processing(str(signal["signal_id"]))

    with factory.connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "order_intents": _table_count(conn, "order_intents"),
        }
    assert after == before


def _table_count(conn, table_name: str) -> int:
    exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table_name,)).fetchone()["table_name"]
    if not exists:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"])
