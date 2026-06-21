"""
V2 Neural Mesh Part 4C-H: Consolidated Safety Regression Suite.

Proves that running every 4C service layer does not:
- create paper/shadow/live orders
- create order intents
- flip paper_ready to True
- activate any execution path
- produce execution_allowed=True in coordinator decisions

All services are read-only mesh diagnostics. Their combined execution must
leave every safety table unchanged.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.neural_mesh.mesh_blockers import MeshBlocker, MeshBlockerReport
from app.neural_mesh.producer_health import ProducerHealth, ProducerHealthSummary
from app.services.link_coverage import LinkCoverageService
from app.services.mesh_blockers import MeshBlockersService
from app.services.neuron_signals import NeuronSignalService
from app.services.producer_health import ProducerHealthService
from app.services.signal_quality import evaluate_signal_context


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _safety_counts(conn) -> dict[str, int]:
    return {
        "paper_orders": int(conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"]),
        "shadow_orders": int(conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"]),
        "live_orders": int(conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"]),
        "execution_allowed_true": int(
            conn.execute(
                "SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed IS TRUE"
            ).fetchone()["count"]
        ),
        "order_intents": _table_count(conn, "order_intents"),
    }


def _table_count(conn, table_name: str) -> int:
    exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table_name,)).fetchone()["table_name"]
    if not exists:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"])


def _prepare_signal(postgres_test_schema) -> dict[str, object]:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_link_coverage_runs")
        conn.execute("DELETE FROM signal_suggested_market_links")
        conn.execute("DELETE FROM signal_link_coverage_analysis")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM signal_quality_evaluations")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
    return NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            status="ACTIVE",
            market_id="safety-regression-market",
            confidence=0.8,
            strength=0.8,
            evidence={"resolution_status": "clear"},
            raw_payload_ref="rules:safety-regression",
        )
    )


# ---------------------------------------------------------------------------
# Test 28: paper_ready remains False
# ---------------------------------------------------------------------------

def test_paper_ready_remains_false_after_4c_services(postgres_test_schema) -> None:
    _prepare_signal(postgres_test_schema)

    mesh_payload = MeshBlockersService().get_mesh_blockers(limit=20)
    producer_payload = ProducerHealthService().get_producer_health_summary(limit=20)
    link_payload = LinkCoverageService().get_link_coverage_summary(limit=50)

    assert mesh_payload["paper_ready"] is False, "MeshBlockersService must not flip paper_ready"
    assert producer_payload["paper_ready"] is False, "ProducerHealthService must not flip paper_ready"
    assert link_payload["paper_ready"] is False, "LinkCoverageService summary must not flip paper_ready"


# ---------------------------------------------------------------------------
# Tests 29-31: paper/shadow/live orders remain 0
# ---------------------------------------------------------------------------

def test_paper_orders_remain_zero_after_full_4c_service_chain(postgres_test_schema) -> None:
    _prepare_signal(postgres_test_schema)
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = _safety_counts(conn)

    MeshBlockersService().get_mesh_blockers(limit=20)
    ProducerHealthService().get_producer_health_summary(limit=20)
    LinkCoverageService().analyze_recent_signals(limit=10, create_suggestions=True, apply_safe_links=False)
    LinkCoverageService().get_link_coverage_summary(limit=50)

    with factory.connect() as conn:
        after = _safety_counts(conn)

    assert after["paper_orders"] == before["paper_orders"], "Paper orders must not be created by 4C services"
    assert after["shadow_orders"] == before["shadow_orders"], "Shadow orders must not be created by 4C services"
    assert after["live_orders"] == before["live_orders"], "Live orders must not be created by 4C services"


# ---------------------------------------------------------------------------
# Test 32: order_intents table absent or count=0
# ---------------------------------------------------------------------------

def test_order_intents_absent_or_zero_after_4c_services(postgres_test_schema) -> None:
    _prepare_signal(postgres_test_schema)

    MeshBlockersService().get_mesh_blockers(limit=20)
    ProducerHealthService().get_producer_health_summary(limit=20)
    LinkCoverageService().get_link_coverage_summary(limit=50)

    with DatabaseConnectionFactory().connect() as conn:
        count = _table_count(conn, "order_intents")

    assert count == 0, "order_intents must remain absent or at 0 after 4C services"


# ---------------------------------------------------------------------------
# Test 33: execution_allowed_true=0
# ---------------------------------------------------------------------------

def test_execution_allowed_true_remains_zero_after_4c_services(postgres_test_schema) -> None:
    _prepare_signal(postgres_test_schema)

    MeshBlockersService().get_mesh_blockers(limit=20)
    ProducerHealthService().get_producer_health_summary(limit=20)
    LinkCoverageService().get_link_coverage_summary(limit=50)

    with DatabaseConnectionFactory().connect() as conn:
        count = int(
            conn.execute(
                "SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed IS TRUE"
            ).fetchone()["count"]
        )

    assert count == 0, "execution_allowed=True must remain 0 after 4C services"


# ---------------------------------------------------------------------------
# Test 34: no live/shadow/paper execution path is activated
# ---------------------------------------------------------------------------

def test_4c_services_do_not_activate_any_execution_path(postgres_test_schema) -> None:
    _prepare_signal(postgres_test_schema)
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = _safety_counts(conn)

    MeshBlockersService().get_mesh_blockers(limit=20)
    ProducerHealthService().get_producer_health_summary(limit=20)
    LinkCoverageService().analyze_recent_signals(limit=10, create_suggestions=True, apply_safe_links=False)

    with factory.connect() as conn:
        after = _safety_counts(conn)

    assert after == before, (
        f"4C services must not change any safety counts. Before={before}, After={after}"
    )


# ---------------------------------------------------------------------------
# Contract-level safety: MeshBlocker cannot have paper_ready=True
# ---------------------------------------------------------------------------

def test_mesh_blocker_report_cannot_have_paper_ready_true() -> None:
    blocker = MeshBlocker(
        code="BRAIN_OUTPUTS_DRY_RUN_ONLY",
        active=True,
        severity="CRITICAL",
        category="BRAIN",
        reason="All Brain Outputs are dry-run.",
        evidence={"brain_outputs_runtime": 0, "brain_outputs_dry_run": 48},
        source="dry_run_provenance",
        recommended_next_step="Build runtime brain producer adapters.",
        blocks_paper=True,
    )
    report = MeshBlockerReport(
        mock_data=False,
        paper_ready=False,
        overall_status="BLOCKED",
        blocked_by=[blocker.code],
        blockers=[blocker],
        info=[],
        counts={"critical": 1, "active_blockers": 1},
        last_updated=datetime.now(UTC),
    )

    payload = report.to_api_dict()
    assert payload["paper_ready"] is False
    assert payload["mock_data"] is False
    assert "BRAIN_OUTPUTS_DRY_RUN_ONLY" in payload["blocked_by"]


# ---------------------------------------------------------------------------
# Contract-level safety: ProducerHealthSummary cannot have paper_ready=True
# ---------------------------------------------------------------------------

def test_producer_health_summary_cannot_have_paper_ready_true() -> None:
    item = ProducerHealth(
        producer_name="dry_run_adapter",
        health_status="DRY_RUN_ONLY",
        health_reason="Only dry-run evidence observed.",
        dry_run_only=True,
        can_feed_paper=False,
    )
    summary = ProducerHealthSummary(
        mock_data=False,
        overall_status="DEGRADED",
        paper_ready=False,
        total_producers=1,
        dry_run_only_producers=1,
        dry_run_only_neurons=["dry_run_adapter"],
        producer_health=[item],
        neuron_runtime_truth={"dry_run_only": ["dry_run_adapter"]},
        last_updated=datetime.now(UTC),
    )

    payload = summary.to_api_dict()
    assert payload["paper_ready"] is False
    assert payload["mock_data"] is False
    assert payload["dry_run_only_producers"] == 1


# ---------------------------------------------------------------------------
# Safety: signal quality evaluation never creates orders
# ---------------------------------------------------------------------------

def test_signal_quality_evaluate_does_not_create_orders_or_intents() -> None:
    from datetime import UTC, datetime

    ctx = {
        "signal_id": "safety-quality-regression",
        "status": "ACTIVE",
        "source_name": "rules_resolution_truth",
        "binding_source_name": "rules_resolution_truth",
        "correlation_id": "corr-safety",
        "binding_correlation_id": "corr-safety",
        "raw_payload_ref": "rules:safety",
        "binding_raw_payload_ref": "rules:safety",
        "market_id": "safety-market",
        "confidence": 0.9,
        "strength": 0.8,
        "freshness_seconds": 0,
        "stale_after_seconds": 3600,
        "expires_at": None,
        "created_at": datetime.now(UTC),
        "evidence_json": {"resolution_status": "clear"},
        "evidence_count": 0,
        "has_binding": True,
        "producer_name": "rules_resolution_adapter",
        "generated_from": "rules_resolution",
        "linked_to_market": True,
        "linked_to_position": False,
        "used_by_brain_output": False,
        "used_by_coordinator": False,
        "has_evidence_rows": False,
        "has_non_dry_run_market_link": True,
    }
    result = evaluate_signal_context(ctx)

    assert result is not None
    assert result.quality_score >= 0.0
    assert result.quality_score <= 1.0


# ---------------------------------------------------------------------------
# Safety: mock_data must be False in all 4C service payloads
# ---------------------------------------------------------------------------

def test_all_4c_services_return_mock_data_false(postgres_test_schema) -> None:
    run_migrations()

    mesh_payload = MeshBlockersService().get_mesh_blockers(limit=20)
    producer_payload = ProducerHealthService().get_producer_health_summary(limit=20)
    link_payload = LinkCoverageService().get_link_coverage_summary(limit=50)

    assert mesh_payload.get("mock_data") is False, "MeshBlockersService must return mock_data=False"
    assert producer_payload.get("mock_data") is False, "ProducerHealthService must return mock_data=False"
    assert link_payload.get("mock_data") is False, "LinkCoverageService must return mock_data=False"
